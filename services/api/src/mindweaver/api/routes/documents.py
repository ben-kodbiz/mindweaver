"""Document library endpoints."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver import storage
from mindweaver.api.schemas import DocumentList, DocumentRead, ProcessingJobRead
from mindweaver.chunking.model import Chunk
from mindweaver.database import session_scope
from mindweaver.documents import (
    DuplicateDocumentError,
    EmptyFileError,
    FileTooLargeError,
    InvalidPdfError,
    delete_document,
    get_document,
    list_documents,
    load_canonical_document,
    reprocess_document,
    reprocess_with_ocr,
    upload_pdf,
)
from mindweaver.graph.types import GraphRead
from mindweaver.mindmap.types import (
    ExpandResult,
    ExplainResult,
    MindMap,
    NodeEvidence,
    RelatedNode,
)
from mindweaver.models import Document, ProcessingJob

router = APIRouter(tags=["documents"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


def _document_or_404(session: Session, document_id: str) -> Document:
    document = get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(_session),
) -> DocumentRead:
    settings = request.app.state.settings
    try:
        document = upload_pdf(session, settings, filename=file.filename or "", file=file.file)
    except EmptyFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InvalidPdfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"duplicate document: {exc.existing.id}",
        ) from exc
    return DocumentRead.model_validate(document)


@router.get("", response_model=DocumentList)
def list_documents_endpoint(
    session: Session = Depends(_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DocumentList:
    documents, total = list_documents(session, limit=limit, offset=offset)
    return DocumentList(items=[DocumentRead.model_validate(d) for d in documents], total=total)


@router.get("/{document_id}", response_model=DocumentRead)
def get_document_endpoint(document_id: str, session: Session = Depends(_session)) -> DocumentRead:
    return DocumentRead.model_validate(_document_or_404(session, document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_endpoint(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> None:
    document = _document_or_404(session, document_id)
    delete_document(session, request.app.state.settings, document)


@router.post("/{document_id}/reprocess", response_model=DocumentRead)
def reprocess_document_endpoint(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> DocumentRead:
    document = _document_or_404(session, document_id)
    return DocumentRead.model_validate(
        reprocess_document(session, request.app.state.settings, document)
    )


@router.post("/{document_id}/reprocess-ocr", response_model=DocumentRead)
def reprocess_ocr_endpoint(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> DocumentRead:
    document = _document_or_404(session, document_id)
    return DocumentRead.model_validate(
        reprocess_with_ocr(session, request.app.state.settings, document)
    )


@router.get("/{document_id}/file")
def download_original(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> FileResponse:
    document = _document_or_404(session, document_id)
    version = document.versions[-1]
    path = storage.original_path(request.app.state.settings, version.storage_key)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="original file missing")
    return FileResponse(path, media_type="application/pdf", filename=document.original_filename)


@router.get("/{document_id}/content")
def get_document_content(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> dict[str, object]:
    document = _document_or_404(session, document_id)
    content = load_canonical_document(request.app.state.settings, document)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document content not available yet",
        )
    return content


@router.get("/{document_id}/chunks", response_model=list[Chunk])
def get_document_chunks(document_id: str, session: Session = Depends(_session)) -> list[Chunk]:
    _document_or_404(session, document_id)
    from mindweaver.chunking.service import chunk_record_to_model, list_chunks

    return [chunk_record_to_model(record) for record in list_chunks(session, document_id)]


@router.get("/{document_id}/graph", response_model=GraphRead)
def get_document_graph(document_id: str, session: Session = Depends(_session)) -> GraphRead:
    _document_or_404(session, document_id)
    from mindweaver.graph.service import get_graph

    graph = get_graph(session, document_id)
    if graph is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="graph not available yet")
    return graph


@router.get("/{document_id}/mindmap", response_model=MindMap)
def get_document_mindmap(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> MindMap:
    document = _document_or_404(session, document_id)
    from mindweaver.mindmap.service import generate_mindmap

    mindmap = generate_mindmap(session, request.app.state.settings, document)
    if mindmap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="mind map not available yet"
        )
    return mindmap


@router.get("/{document_id}/mindmap/preferences")
def get_mindmap_preferences(
    document_id: str, session: Session = Depends(_session)
) -> dict[str, object]:
    _document_or_404(session, document_id)
    from mindweaver.mindmap.service import get_preferences

    return get_preferences(session, document_id)


@router.put("/{document_id}/mindmap/preferences")
def put_mindmap_preferences(
    document_id: str,
    payload: dict[str, object],
    session: Session = Depends(_session),
) -> dict[str, object]:
    _document_or_404(session, document_id)
    from mindweaver.mindmap.service import set_preferences

    set_preferences(session, document_id, payload)
    return payload


@router.get("/{document_id}/mindmap/nodes/{node_id}/evidence", response_model=NodeEvidence)
def node_evidence_endpoint(
    request: Request, document_id: str, node_id: str, session: Session = Depends(_session)
) -> NodeEvidence:
    document = _document_or_404(session, document_id)
    from mindweaver.mindmap.actions import node_evidence

    return node_evidence(session, request.app.state.settings, document, node_id)


@router.get("/{document_id}/mindmap/nodes/{node_id}/related", response_model=list[RelatedNode])
def node_related_endpoint(
    request: Request, document_id: str, node_id: str, session: Session = Depends(_session)
) -> list[RelatedNode]:
    document = _document_or_404(session, document_id)
    from mindweaver.mindmap.actions import related_nodes

    return related_nodes(session, request.app.state.settings, document, node_id)


@router.post("/{document_id}/mindmap/nodes/{node_id}/expand", response_model=ExpandResult)
def node_expand_endpoint(
    request: Request, document_id: str, node_id: str, session: Session = Depends(_session)
) -> ExpandResult:
    document = _document_or_404(session, document_id)
    from mindweaver.mindmap.actions import expand_node

    try:
        return expand_node(session, request.app.state.settings, document, node_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"expansion failed: {exc}",
        ) from exc


@router.post("/{document_id}/mindmap/nodes/{node_id}/explain", response_model=ExplainResult)
def node_explain_endpoint(
    request: Request, document_id: str, node_id: str, session: Session = Depends(_session)
) -> ExplainResult:
    document = _document_or_404(session, document_id)
    from mindweaver.mindmap.actions import explain_node

    return explain_node(session, request.app.state.settings, document, node_id)


class NodeAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@router.post("/{document_id}/mindmap/nodes/{node_id}/ask")
def node_ask_endpoint(
    request: Request,
    document_id: str,
    node_id: str,
    payload: NodeAskRequest,
    session: Session = Depends(_session),
) -> dict[str, object]:
    document = _document_or_404(session, document_id)
    from mindweaver.chat.service import create_session
    from mindweaver.mindmap.actions import ask_node

    chat_session = create_session(session, document_id=document.id)
    import json as _json

    chat_session.context = _json.dumps({"node_id": node_id})
    session.flush()
    result = ask_node(session, request.app.state.settings, document, node_id, payload.question)
    return {
        "session_id": chat_session.id,
        "question": result.question,
        "answer": result.answer,
        "grounding": result.grounding,
        "citations": [citation.model_dump() for citation in result.citations],
    }


@router.post("/{document_id}/graph/extract", response_model=GraphRead)
def extract_document_graph(
    request: Request, document_id: str, session: Session = Depends(_session)
) -> GraphRead:
    document = _document_or_404(session, document_id)
    from mindweaver.graph.service import get_graph, run_graph_extraction

    run_graph_extraction(session, request.app.state.settings, document)
    graph = get_graph(session, document_id)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="graph extraction produced no graph",
        )
    return graph


@router.get("/{document_id}/chunks/{chunk_id}/source")
def chunk_source_endpoint(
    request: Request,
    document_id: str,
    chunk_id: str,
    session: Session = Depends(_session),
) -> dict[str, object]:
    document = _document_or_404(session, document_id)
    from mindweaver.documents import chunk_source_regions

    regions = chunk_source_regions(session, request.app.state.settings, document, chunk_id)
    if regions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    return regions


class SelectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    page_number: int = Field(default=1, ge=1)
    confirm: bool = False


@router.post("/{document_id}/mindmap/selection")
def mindmap_selection_endpoint(
    request: Request,
    document_id: str,
    payload: SelectionRequest,
    session: Session = Depends(_session),
) -> dict[str, object]:
    document = _document_or_404(session, document_id)
    from mindweaver.graph.selection import extract_selection

    return extract_selection(
        session,
        request.app.state.settings,
        document,
        payload.text,
        payload.page_number,
        confirm=payload.confirm,
    )


@router.get("/{document_id}/jobs", response_model=list[ProcessingJobRead])
def document_jobs(
    document_id: str, session: Session = Depends(_session)
) -> list[ProcessingJobRead]:
    _document_or_404(session, document_id)
    jobs = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
    ).all()
    return [ProcessingJobRead.model_validate(job) for job in jobs]
