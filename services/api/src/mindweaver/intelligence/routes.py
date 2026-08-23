"""Stage 7: intelligence API — namespaced, feature-flagged, additive."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindweaver.database import session_scope
from mindweaver.intelligence.config import IntelligenceConfig

router = APIRouter(tags=["intelligence"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


def _intel_config(request: Request) -> IntelligenceConfig:
    config = request.app.state.settings.intelligence
    if isinstance(config, IntelligenceConfig):
        return config
    return IntelligenceConfig.model_validate(config)


class _Disabled(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Intelligence features are disabled",
        )


def _gateway(request: Request) -> object:
    gateway = getattr(request.app.state, "intelligence_gateway", None)
    if gateway is None:
        raise _Disabled()
    return gateway


@router.get("/status")
def status_endpoint(request: Request) -> dict[str, object]:
    config = _intel_config(request)
    return {
        "enabled": config.enabled,
        "text_model": {
            "enabled": config.text.enabled,
            "model": config.text.model,
            "capabilities": config.text.capabilities.model_dump(),
        },
        "vision_model": {
            "enabled": config.vision.enabled,
            "model": config.vision.model,
            "capabilities": config.vision.capabilities.model_dump(),
        },
        "tools": {"enabled": config.tools.enabled},
        "node_expansion": {"enabled": config.node_expansion.enabled},
    }


@router.get("/health")
def health_endpoint(request: Request) -> dict[str, Any]:
    """Runtime health check — probes model endpoints for reachability."""
    config = _intel_config(request)
    if not config.enabled:
        return {"enabled": False, "text": {}, "vision": {}}

    gateway_obj = getattr(request.app.state, "intelligence_gateway", None)
    if gateway_obj is None:
        return {"enabled": True, "text": {"reachable": False}, "vision": {"reachable": False}}

    from mindweaver.intelligence.gateway import IntelligenceGateway

    if isinstance(gateway_obj, IntelligenceGateway):
        return {"enabled": True, **gateway_obj.health_check()}
    return {"enabled": True, "text": {}, "vision": {}}


@router.get("/models")
def models_endpoint(request: Request) -> dict[str, object]:
    config = _intel_config(request)
    from mindweaver.intelligence.config import PRESETS

    return {
        "enabled": config.enabled,
        "presets": sorted(PRESETS.keys()),
        "text": config.text.model_dump(),
        "vision": config.vision.model_dump(),
    }


class VisionAnalyzeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)


@router.post("/vision/analyze")
def vision_analyze_endpoint(
    request: Request,
    payload: VisionAnalyzeRequest,
    session: Session = Depends(_session),
) -> dict[str, object]:
    config = _intel_config(request)
    if not config.enabled or not config.vision_analysis.enabled:
        raise _Disabled()

    from mindweaver.documents import get_document
    from mindweaver.intelligence.vision import escalate_with_fallback, save_interpretation
    from mindweaver.storage import original_path

    document = get_document(session, payload.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    version = document.versions[-1]
    pdf_path = str(original_path(request.app.state.settings, version.storage_key))

    gateway: Any = _gateway(request)
    interpretation, fallback_note = escalate_with_fallback(
        settings=request.app.state.settings,
        intel_config=config.vision_analysis,
        vision_model=gateway.vision,
        pdf_path=pdf_path,
        page_number=payload.page_number,
        ocr_result=None,
    )
    if interpretation is None:
        return {"analyzed": False, "note": fallback_note}

    save_interpretation(request.app.state.settings, document.id, interpretation)
    return {"analyzed": True, "interpretation": interpretation.to_dict()}


@router.post("/mindmap/expand")
def mindmap_expand_endpoint(
    request: Request,
    document_id: str,
    node_id: str,
    session: Session = Depends(_session),
) -> dict[str, object]:
    """Return an AI expansion PROPOSAL. Nothing enters the graph here.

    Both ``document_id`` and ``node_id`` are query parameters (empty POST body).
    """
    config = _intel_config(request)
    if not config.enabled or not config.node_expansion.enabled:
        raise _Disabled()

    from mindweaver.documents import get_document

    document = get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    if not node_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="node_id query parameter is required",
        )

    from mindweaver.intelligence.expansion import propose_with_gateway

    gateway: Any = _gateway(request)
    try:
        proposal = propose_with_gateway(
            session,
            request.app.state.settings,
            config,
            gateway,
            document,
            node_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "proposal": proposal.to_dict(),
        "tool_log": proposal.tool_log,
        "status_hint": "review required - nothing added to the graph yet",
    }


class AcceptChild(BaseModel):
    label: str
    relationship: str = "related"
    description: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class AcceptRequest(BaseModel):
    children: list[AcceptChild] = Field(default_factory=list)


@router.post("/mindmap/nodes/{node_id}/accept")
def accept_proposal_endpoint(
    request: Request,
    document_id: str,
    node_id: str,
    payload: AcceptRequest,
    session: Session = Depends(_session),
) -> dict[str, object]:
    """Commit user-accepted children of a proposal into the personal layer."""
    config = _intel_config(request)
    if not config.enabled or not config.node_expansion.enabled:
        raise _Disabled()

    from mindweaver.documents import get_document
    from mindweaver.graph.user_edits import (
        EditError as UserEditError,
    )
    from mindweaver.graph.user_edits import (
        add_personal_node,
        create_connection,
    )

    document = get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    created: list[dict[str, object]] = []
    errors: list[str] = []
    for child in payload.children:
        try:
            node = add_personal_node(
                session,
                request.app.state.settings,
                document,
                label=child.label,
                note=child.description,
                ai_accepted=True,
            )
            evidence = (child.evidence or [{}])[0]
            page_note = f"page {evidence.get('page_number')}" if evidence else ""
            create_connection(
                session,
                request.app.state.settings,
                document,
                source=node_id,
                target=node.id,
                relation="related_to",
                note=f"AI proposal; {page_note}".strip(),
            )
            created.append({"id": node.id, "label": node.label})
        except UserEditError as exc:
            errors.append(str(exc))
        except Exception as exc:  # duplicate connection etc.
            errors.append(f"{child.label}: {exc}")

    return {
        "accepted_count": len(created),
        "created": created,
        "errors": errors,
    }
