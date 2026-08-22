"""Stage 17: job system — progress, cancellation, retry, recovery."""

from fixtures.pdf import make_search_book_pdf
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.jobs import JobContext, recover_stale_jobs, submit_job
from mindweaver.models import ChunkRecord, Document, JobStatus, JobType, ProcessingJob


def _settings(tmp_path):
    settings = Settings(database=DatabaseConfig(url=f"sqlite:///{tmp_path}/j.db"))
    settings.llm.provider = "stub"
    return settings


def _setup(session):
    session.add(
        Document(id="doc_1", title="B", original_filename="b.pdf", sha256="a" * 64, file_size=1)
    )
    session.flush()
    return session.get(Document, "doc_1")


def test_job_lifecycle_with_progress(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        document = _setup(session)

        def handler(ctx: JobContext) -> None:
            ctx.append_log("step one")
            ctx.set_progress(0.5)
            ctx.checkpoint({"stage": "half"})
            ctx.set_progress(1.0)

        from mindweaver.jobs import get_job_logs

        job = submit_job(session, None, document, JobType.DOCUMENT_EXTRACTION, handler)
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 1.0
        logs = get_job_logs(session, job.id)
        assert "step one" in (logs or "")


def test_cancellation_mid_job(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        document = _setup(session)

        def cancelling_handler(ctx: JobContext) -> None:
            # user cancels right after the job starts running
            from sqlalchemy import update

            ctx.session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == ctx.job_id)
                .values(status=JobStatus.CANCELLED)
            )
            ctx.set_progress(0.2)
            ctx.checkpoint({"stage": "before-cancel"})  # raises JobCancelled

        job = submit_job(session, None, document, JobType.DOCUMENT_EXTRACTION, cancelling_handler)
        # the runner marks the job cancelled; no partial completion
        assert job.status == JobStatus.CANCELLED
        assert job.progress != 1.0


def test_retry_policy_then_failure(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        document = _setup(session)
        calls = {"count": 0}

        def flaky_handler(ctx: JobContext) -> None:
            calls["count"] += 1
            raise RuntimeError(f"boom {calls['count']}")

        job = submit_job(
            session,
            None,
            document,
            JobType.DOCUMENT_EXTRACTION,
            flaky_handler,
            max_attempts=3,
        )
        assert job.status == JobStatus.FAILED
        assert calls["count"] == 3  # retried until max_attempts
        assert "boom 3" in (job.error_message or "")


def test_recovery_marks_stale_jobs_failed(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        document = _setup(session)
        stale = ProcessingJob(
            document_id=document.id,
            job_type=JobType.DOCUMENT_EXTRACTION,
            status=JobStatus.RUNNING,
        )
        session.add(stale)
        session.flush()

        count = recover_stale_jobs(session)
        assert count >= 1
        session.refresh(stale)
        assert stale.status == JobStatus.FAILED
        assert "retry" in (stale.error_message or "")


def test_checkpoint_resume_is_idempotent(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        document = _setup(session)
        runs = {"n": 0}

        def idempotent_handler(ctx: JobContext) -> None:
            runs["n"] += 1
            ctx.checkpoint({"run": runs["n"]})
            existing = ctx.session.query(ChunkRecord).count()
            if not existing:
                ctx.session.add(
                    ChunkRecord(
                        chunk_id="only",
                        document_id="doc_1",
                        position=0,
                        page_start=1,
                        page_end=1,
                        chapter=None,
                        section=None,
                        subsection=None,
                        section_path="[]",
                        text="idempotent write",
                        token_count=2,
                        parent_chunk_id=None,
                    )
                )

        submit_job(session, None, document, JobType.CHUNKING, idempotent_handler)
        first_count = session.query(ChunkRecord).count()

        # second run must not duplicate work
        submit_job(session, None, document, JobType.CHUNKING, idempotent_handler)
        assert session.query(ChunkRecord).count() == first_count == 1


def test_async_process_endpoint(client, app_settings):
    app_settings.llm.provider = "stub"
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_search_book_pdf(), "application/pdf")},
    )
    doc_id = resp.json()["id"]

    resp = client.post(f"/api/v1/documents/{doc_id}/process")
    assert resp.status_code == 200
    body = resp.json()
    if body["status"] != "completed":  # surface handler errors in the assert
        detail = client.get(f"/api/v1/jobs/{body['job_id']}")
        raise AssertionError(f"job failed: {detail.json()}")
    assert body["status"] == "completed"

    job_id = body["job_id"]
    detail = client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["status"] == "completed"
    assert detail["progress"] == 1.0

    logs = client.get(f"/api/v1/jobs/{job_id}/logs").json()
    assert "metadata extraction" in logs["logs"]

    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "completed"  # already finished; no-op
