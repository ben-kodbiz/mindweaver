"""Notebook endpoints: cross-document workspaces."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindweaver.database import session_scope
from mindweaver.models import Notebook
from mindweaver.notebooks import (
    NotebookError,
    add_document,
    compare_documents,
    create_notebook,
    delete_notebook,
    get_notebook,
    list_documents,
    list_notebooks,
    notebook_graph,
    remove_document,
    search_notebook,
)

router = APIRouter(tags=["notebooks"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


class NotebookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)


class NotebookDocumentAdd(BaseModel):
    document_id: str = Field(min_length=1)


def _notebook_or_404(session: Session, notebook_id: str) -> Notebook:
    notebook = get_notebook(session, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notebook not found")
    return notebook


@router.post("", status_code=status.HTTP_201_CREATED)
def create_notebook_endpoint(
    payload: NotebookCreate, session: Session = Depends(_session)
) -> dict[str, object]:
    try:
        notebook = create_notebook(session, title=payload.title, description=payload.description)
    except NotebookError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "id": notebook.id,
        "title": notebook.title,
        "description": notebook.description,
        "document_count": 0,
    }


@router.get("")
def list_notebooks_endpoint(session: Session = Depends(_session)) -> list[dict[str, Any]]:
    return list_notebooks(session)


@router.get("/{notebook_id}")
def get_notebook_endpoint(
    notebook_id: str, session: Session = Depends(_session)
) -> dict[str, object]:
    notebook = _notebook_or_404(session, notebook_id)
    documents = [
        {
            "id": doc.id,
            "title": doc.title,
            "original_filename": doc.original_filename,
            "status": doc.status.value if hasattr(doc.status, "value") else doc.status,
            "page_count": doc.page_count,
        }
        for doc in list_documents(session, notebook_id)
    ]
    return {
        "id": notebook.id,
        "title": notebook.title,
        "description": notebook.description,
        "documents": documents,
    }


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook_endpoint(notebook_id: str, session: Session = Depends(_session)) -> None:
    delete_notebook(session, _notebook_or_404(session, notebook_id))


@router.post("/{notebook_id}/documents", status_code=status.HTTP_201_CREATED)
def add_document_endpoint(
    notebook_id: str,
    payload: NotebookDocumentAdd,
    session: Session = Depends(_session),
) -> dict[str, object]:
    notebook = _notebook_or_404(session, notebook_id)
    from mindweaver.models import Document

    try:
        add_document(session, notebook, payload.document_id)
    except NotebookError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    document = session.get(Document, payload.document_id)
    return {
        "notebook_id": notebook.id,
        "document_id": payload.document_id,
        "title": document.title if document else None,
    }


@router.delete("/{notebook_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document_endpoint(
    notebook_id: str, document_id: str, session: Session = Depends(_session)
) -> None:
    notebook = _notebook_or_404(session, notebook_id)
    remove_document(session, notebook, document_id)


@router.get("/{notebook_id}/search")
def search_notebook_endpoint(
    request: Request,
    notebook_id: str,
    q: str = Query(..., min_length=1),
    limit: int | None = Query(default=None, ge=1, le=100),
    session: Session = Depends(_session),
) -> dict[str, object]:
    notebook = _notebook_or_404(session, notebook_id)
    return search_notebook(session, request.app.state.settings, notebook, q, limit=limit)


@router.get("/{notebook_id}/graph")
def notebook_graph_endpoint(
    notebook_id: str, session: Session = Depends(_session)
) -> dict[str, object]:
    notebook = _notebook_or_404(session, notebook_id)
    return notebook_graph(session, notebook)


@router.get("/{notebook_id}/compare")
def compare_notebook_endpoint(
    notebook_id: str, session: Session = Depends(_session)
) -> dict[str, object]:
    notebook = _notebook_or_404(session, notebook_id)
    return compare_documents(session, notebook)
