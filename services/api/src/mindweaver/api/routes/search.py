"""Search endpoints."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from mindweaver.database import session_scope
from mindweaver.search.base import SearchResponse
from mindweaver.search.service import search as run_search

router = APIRouter(tags=["search"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


@router.get("", response_model=SearchResponse)
def search_documents(
    request: Request,
    q: str = Query(..., min_length=1),
    document_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=100),
    session: Session = Depends(_session),
) -> SearchResponse:
    return run_search(
        session,
        request.app.state.settings,
        q,
        document_id=document_id,
        limit=limit,
    )
