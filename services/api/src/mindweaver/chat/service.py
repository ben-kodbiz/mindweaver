"""Chat session management: persistence of conversations and answers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mindweaver.chat.rag import answer_question
from mindweaver.chat.types import AnswerResult
from mindweaver.config import Settings
from mindweaver.models import ChatCitation, ChatMessage, ChatSession


def create_session(session: Session, *, document_id: str | None = None) -> ChatSession:
    chat_session = ChatSession(document_id=document_id)
    session.add(chat_session)
    session.flush()
    return chat_session


def list_sessions(session: Session) -> list[ChatSession]:
    return list(session.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc())).all())


def get_session(session: Session, session_id: str) -> ChatSession | None:
    return session.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages).selectinload(ChatMessage.citations))
    )


def delete_session(session: Session, chat_session: ChatSession) -> None:
    session.delete(chat_session)


def ask(
    session: Session,
    settings: Settings,
    chat_session: ChatSession,
    question: str,
) -> AnswerResult:
    user_message = ChatMessage(session_id=chat_session.id, role="user", content=question)
    session.add(user_message)
    session.flush()

    result = answer_question(session, settings, question, document_id=chat_session.document_id)

    assistant = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content=result.answer,
        grounding=result.grounding,
    )
    session.add(assistant)
    session.flush()

    for position, citation in enumerate(result.citations):
        session.add(
            ChatCitation(
                message_id=assistant.id,
                chunk_id=citation.chunk_id,
                document_id=citation.document_id,
                page_start=citation.page_start,
                page_end=citation.page_end,
                chapter=citation.chapter,
                section=citation.section,
                position=position,
            )
        )
    session.flush()
    return result
