from __future__ import annotations

from app.db import get_session
from app.repositories import get_job, set_job_progress


def set_job_progress_if_active(job_id: int, *, percent: int, message: str | None) -> None:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None:
            return
        if job.status not in {"queued", "running"}:
            return
        set_job_progress(
            session,
            job,
            progress_percent=percent,
            progress_message=message,
        )
