"""Chat endpoints."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindweaver.chat.service import (
    ask,
    create_session,
    delete_session,
    get_session,
    list_sessions,
)
from mindweaver.chat.types import Citation
from mindweaver.database import session_scope
from mindweaver.models import ChatMessage, ChatSession

router = APIRouter(tags=["chat"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


class ChatSessionCreate(BaseModel):
    document_id: str | None = None


class ChatSessionRead(BaseModel):
    id: str
    document_id: str | None
    created_at: str
    updated_at: str


class ChatMessageRead(BaseModel):
    id: str
    role: str
    content: str
    grounding: str | None
    citations: list[Citation]
    created_at: str


class ChatSessionDetail(BaseModel):
    id: str
    document_id: str | None
    messages: list[ChatMessageRead]
    created_at: str
    updated_at: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatAnswer(BaseModel):
    session_id: str
    question: str
    answer: str
    grounding: str
    citations: list[Citation]


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
def create_chat_session(
    payload: ChatSessionCreate, session: Session = Depends(_session)
) -> ChatSessionRead:
    chat_session = create_session(session, document_id=payload.document_id)
    return _read_session(chat_session)


@router.get("/sessions", response_model=list[ChatSessionRead])
def list_chat_sessions(session: Session = Depends(_session)) -> list[ChatSessionRead]:
    return [_read_session(item) for item in list_sessions(session)]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(session_id: str, session: Session = Depends(_session)) -> ChatSessionDetail:
    chat_session = _session_or_404(session, session_id)
    return ChatSessionDetail(
        id=chat_session.id,
        document_id=chat_session.document_id,
        messages=[_read_message(message) for message in chat_session.messages],
        created_at=chat_session.created_at.isoformat(),
        updated_at=chat_session.updated_at.isoformat(),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(session_id: str, session: Session = Depends(_session)) -> None:
    delete_session(session, _session_or_404(session, session_id))


@router.post("/sessions/{session_id}/messages", response_model=ChatAnswer)
def send_message(
    request: Request,
    session_id: str,
    payload: ChatRequest,
    session: Session = Depends(_session),
) -> ChatAnswer:
    chat_session = _session_or_404(session, session_id)
    result = ask(session, request.app.state.settings, chat_session, payload.question)
    return ChatAnswer(
        session_id=chat_session.id,
        question=result.question,
        answer=result.answer,
        grounding=result.grounding,
        citations=result.citations,
    )


def _session_or_404(session: Session, session_id: str) -> ChatSession:
    chat_session = get_session(session, session_id)
    if chat_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat session not found")
    return chat_session


def _read_session(chat_session: ChatSession) -> ChatSessionRead:
    return ChatSessionRead(
        id=chat_session.id,
        document_id=chat_session.document_id,
        created_at=chat_session.created_at.isoformat(),
        updated_at=chat_session.updated_at.isoformat(),
    )


def _read_message(message: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        grounding=message.grounding,
        citations=[
            Citation(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                page_start=c.page_start,
                page_end=c.page_end,
                chapter=c.chapter,
                section=c.section,
            )
            for c in message.citations
        ],
        created_at=message.created_at.isoformat(),
    )
