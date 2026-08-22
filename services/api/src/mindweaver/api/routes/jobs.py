"""Processing job endpoints."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindweaver.api.schemas import ProcessingJobRead
from mindweaver.database import session_scope
from mindweaver.models import ProcessingJob

router = APIRouter(tags=["jobs"])


def _session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.session_factory) as session:
        yield session


@router.get("", response_model=list[ProcessingJobRead])
def list_jobs(
    session: Session = Depends(_session),
    document_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ProcessingJobRead]:
    statement = select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit)
    if document_id is not None:
        statement = statement.where(ProcessingJob.document_id == document_id)
    jobs = session.scalars(statement).all()
    return [ProcessingJobRead.model_validate(job) for job in jobs]


@router.post("/{job_id}/cancel", response_model=ProcessingJobRead)
def cancel_job_endpoint(
    request: Request, job_id: str, session: Session = Depends(_session)
) -> ProcessingJobRead:
    from mindweaver.jobs import cancel_job

    job = cancel_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return ProcessingJobRead.model_validate(job)


@router.get("/{job_id}/logs")
def job_logs_endpoint(job_id: str, session: Session = Depends(_session)) -> dict[str, str]:
    from mindweaver.jobs import get_job_logs

    logs = get_job_logs(session, job_id)
    if logs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return {"job_id": job_id, "logs": logs}


@router.get("/{job_id}", response_model=ProcessingJobRead)
def get_job(job_id: str, session: Session = Depends(_session)) -> ProcessingJobRead:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return ProcessingJobRead.model_validate(job)
