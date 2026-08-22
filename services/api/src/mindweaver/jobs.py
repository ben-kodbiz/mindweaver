"""Stage 17: background job system with progress, cancellation, retry and
recovery.

Jobs run through :class:`JobRunner`, which owns the full state machine
(``QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED``), cooperative
cancellation, bounded retries with checkpoints, and stale-job recovery on
startup (a job left ``RUNNING`` by a crashed process is marked ``FAILED`` so
it can be retried safely).
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from mindweaver.models import Document, JobStatus, JobType, ProcessingJob
from mindweaver.models.document import utcnow

MAX_LOG_CHARS = 8000


class JobCancelledError(Exception):
    """Raised inside a handler when cancellation is observed."""


@dataclass
class JobContext:
    """Handler-facing API: progress, checkpoints, cancellation."""

    session: Session
    settings: Any
    document: Document
    job_id: str

    def set_progress(self, value: float, message: str | None = None) -> None:
        job = self._job()
        if job is None:
            return
        job.progress = max(0.0, min(1.0, value))
        if message:
            self.append_log(message)
        self.session.flush()

    def checkpoint(self, state: dict[str, Any]) -> bool:
        """Persist resume information; returns False when the job was cancelled."""
        if self.is_cancelled():
            raise JobCancelledError()
        job = self._job()
        if job is not None:
            job.checkpoint = json.dumps(state)
            self.session.flush()
        return True

    def is_cancelled(self) -> bool:
        status = self.session.scalar(
            select(ProcessingJob.status).where(ProcessingJob.id == self.job_id)
        )
        return status == JobStatus.CANCELLED

    def append_log(self, message: str) -> None:
        job = self._job()
        if job is None:
            return
        line = f"{message}\n"
        job.logs = ((job.logs or "") + line)[-MAX_LOG_CHARS:]
        self.session.flush()

    def _job(self) -> ProcessingJob | None:
        from sqlalchemy import select as _select

        return self.session.scalar(_select(ProcessingJob).where(ProcessingJob.id == self.job_id))


from sqlalchemy import select  # noqa: E402  (kept after class for readability)

JobHandler = Callable[[JobContext], Any]


def recover_stale_jobs(session: Session) -> int:
    """On startup: any job left RUNNING/QUEUED by a dead process fails safely."""
    stale = session.scalars(
        select(ProcessingJob).where(ProcessingJob.status.in_([JobStatus.RUNNING, JobStatus.QUEUED]))
    ).all()
    count = 0
    for job in stale:
        job.status = JobStatus.FAILED
        job.error_message = "interrupted by application restart; safe to retry"
        job.completed_at = job.updated_at
        count += 1
    session.flush()
    return count


def submit_job(
    session: Session,
    settings: Any,
    document: Document,
    job_type: JobType,
    handler: JobHandler,
    *,
    max_attempts: int = 1,
) -> ProcessingJob:
    """Create a QUEUED job and execute it inline with full lifecycle tracking."""
    job = ProcessingJob(
        document_id=document.id,
        job_type=job_type,
        status=JobStatus.QUEUED,
        max_attempts=max_attempts,
    )
    session.add(job)
    session.flush()

    ctx = JobContext(session=session, settings=settings, document=document, job_id=job.id)
    attempts = 0
    while attempts < max(1, job.max_attempts):
        attempts += 1
        job.attempts = attempts
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or utcnow()
        session.flush()
        try:
            handler(ctx)
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.completed_at = __import__(
                "mindweaver.models.document", fromlist=["utcnow"]
            ).utcnow()
            session.flush()
            return job
        except JobCancelledError:
            job.status = JobStatus.CANCELLED
            job.error_message = "cancelled by user"
            job.completed_at = __import__(
                "mindweaver.models.document", fromlist=["utcnow"]
            ).utcnow()
            session.flush()
            return job
        except Exception as exc:  # retry policy
            job.error_message = str(exc)
            tail = traceback.format_exc()[-MAX_LOG_CHARS:]
            job.logs = ((job.logs or "") + tail)[-MAX_LOG_CHARS:]
            if attempts < max(1, job.max_attempts):
                job.status = JobStatus.QUEUED
                ctx.append_log(f"attempt {attempts} failed: {exc}; retrying")
                continue
            job.status = JobStatus.FAILED
            job.completed_at = __import__(
                "mindweaver.models.document", fromlist=["utcnow"]
            ).utcnow()
            session.flush()
            return job
    return job


def cancel_job(session: Session, job_id: str) -> ProcessingJob | None:
    """Cooperative cancellation: RUNNING jobs observe this at their next
    checkpoint."""
    job = session.get(ProcessingJob, job_id)
    if job is None:
        return None
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        job.status = JobStatus.CANCELLED
        session.flush()
    return job


def get_job_logs(session: Session, job_id: str) -> str | None:
    job = session.get(ProcessingJob, job_id)
    return job.logs if job is not None else None


# Backwards-compatible alias
JobCancelled = JobCancelledError
