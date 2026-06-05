from __future__ import annotations

import time
from threading import Event
from typing import Protocol, TypedDict

from app.config import get_settings
from app.db import get_session
from app.jobs.progress import set_job_progress_if_active
from app.repositories import get_job, update_job
from app.services.conversion_service import convert_file


settings = get_settings()


class ConversionRequestLike(Protocol):
    input_file_id: int
    output_format: str
    crs_handling: str
    target_crs: str | None
    csv_lat_col: str | None
    csv_lon_col: str | None
    csv_input_crs: str


class ConversionParams(TypedDict):
    output_format: str
    target_crs: str | None
    csv_lat_col: str | None
    csv_lon_col: str | None
    csv_input_crs: str
    crs_handling: str


def build_conversion_params(request: ConversionRequestLike) -> ConversionParams:
    return {
        "output_format": request.output_format,
        "target_crs": request.target_crs if request.crs_handling == "transform" else None,
        "csv_lat_col": request.csv_lat_col,
        "csv_lon_col": request.csv_lon_col,
        "csv_input_crs": request.csv_input_crs,
        "crs_handling": request.crs_handling,
    }


def run_conversion_job(job_id: int, request: ConversionRequestLike, cancel_event: Event) -> None:
    params = build_conversion_params(request)
    last_progress_emitted_at = 0.0

    def _progress_callback(message: str, percent: int) -> None:
        nonlocal last_progress_emitted_at
        now = time.monotonic()
        if now - last_progress_emitted_at < 0.6 and percent < 100:
            return
        last_progress_emitted_at = now
        set_job_progress_if_active(
            job_id,
            percent=percent,
            message=message,
        )

    try:
        with get_session() as session:
            convert_file(
                session,
                input_file_id=request.input_file_id,
                data_dir=settings.data_upload_dir,
                output_format=params["output_format"],
                target_crs=params["target_crs"],
                csv_lat_col=params["csv_lat_col"],
                csv_lon_col=params["csv_lon_col"],
                csv_input_crs=params["csv_input_crs"],
                job_id=job_id,
                cancel_check=cancel_event.is_set,
                progress_callback=_progress_callback,
            )
    except Exception as exc:
        with get_session() as session:
            job = get_job(session, job_id)
            if job and job.status in {"queued", "running"}:
                update_job(session, job, status="failed", error_message=str(exc))
