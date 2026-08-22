"""Learning output endpoints (Stage 15)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindweaver.database import session_scope
from mindweaver.learning import LearningError, generate_learning_output

router = APIRouter(tags=["learning"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


class LearningRequest(BaseModel):
    kind: str = Field(pattern="^(summary|key_concepts|qa|flashcards|quiz|study_guide)$")
    scope_type: str = Field(default="document", pattern="^(document|chapter|branch)$")
    target: str | None = Field(default=None, max_length=256)


@router.post("/{document_id}/learning")
def generate_learning_endpoint(
    request: Request,
    document_id: str,
    payload: LearningRequest,
    session: Session = Depends(_session),
) -> dict[str, object]:
    from mindweaver.documents import get_document

    document = get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    try:
        return generate_learning_output(
            session,
            request.app.state.settings,
            document,
            kind=payload.kind,  # type: ignore[arg-type]
            scope_type=payload.scope_type,
            target=payload.target,
        )
    except LearningError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
