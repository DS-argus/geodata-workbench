from __future__ import annotations

import time
from threading import Event
from typing import Any, Protocol

from app.collectors import WfsCollectionCancelledError, collect_vworld_layer
from app.config import get_settings
from app.db import get_session
from app.jobs.progress import set_job_progress_if_active
from app.repositories import create_dataset, create_file, get_job, update_job
from app.services.geodata_metadata import bbox_dict, geom_type, serialize_schema
from app.services.secrets_service import VWORLD_SECRET_KEY, get_secret_value


settings = get_settings()


class DumpableFilter(Protocol):
    def model_dump(self) -> dict[str, Any]: ...


class WfsCollectionRequestLike(Protocol):
    layer_key: str
    output_format: str
    srs_name: str
    filters: list[DumpableFilter] | None
    bbox_split: int
    max_features: int | None


def build_wfs_request_params(request: WfsCollectionRequestLike) -> dict[str, Any]:
    return {
        "layer_key": request.layer_key,
        "output_format": request.output_format,
        "srs_name": request.srs_name,
        "filters": [item.model_dump() for item in (request.filters or [])],
        "bbox_split": request.bbox_split,
        "max_features": request.max_features,
    }


def run_wfs_job(job_id: int, request: WfsCollectionRequestLike, cancel_event: Event) -> None:
    with get_session() as session:
        api_key = settings.vworld_api_key or get_secret_value(session, VWORLD_SECRET_KEY)
    if not api_key:
        with get_session() as session:
            job = get_job(session, job_id)
            if job and job.status in {"queued", "running"}:
                update_job(
                    session,
                    job,
                    status="failed",
                    error_message="VWorld API 키가 설정되지 않았습니다.",
                    progress_percent=0,
                    progress_message="API 키가 설정되지 않았습니다.",
                )
        return

    params = build_wfs_request_params(request)

    try:
        with get_session() as session:
            job = get_job(session, job_id)
            if job is None:
                raise ValueError(f"WFS job id {job_id} does not exist.")
            job.status = "running"
            job.error_message = None
            job.finished_at = None
            job.progress_percent = 1
            job.progress_message = "WFS 요청을 준비하는 중입니다."
            session.add(job)
            session.flush()

        last_progress_percent = 1
        last_progress_message = "WFS 요청을 준비하는 중입니다."
        last_progress_emitted_at = 0.0

        def _progress_callback(message: str, percent: int) -> None:
            nonlocal last_progress_percent, last_progress_message, last_progress_emitted_at
            normalized_percent = max(0, min(100, int(percent)))
            normalized_message = (message or "").strip()
            now = time.monotonic()
            should_emit = (
                normalized_percent == 100
                or normalized_percent >= last_progress_percent + 2
                or normalized_message != last_progress_message
                or now - last_progress_emitted_at >= 0.8
            )
            if not should_emit:
                return
            last_progress_percent = normalized_percent
            last_progress_message = normalized_message
            last_progress_emitted_at = now
            set_job_progress_if_active(
                job_id,
                percent=normalized_percent,
                message=normalized_message or None,
            )

        output_path, gdf, collect_stats = collect_vworld_layer(
            api_key=api_key,
            layer_typename=request.layer_key,
            output_format=request.output_format,
            data_dir=settings.data_wfs_dir,
            srs_name=request.srs_name,
            catalog_path=settings.wfs_catalog_path,
            filters=params["filters"] or None,
            bbox_split=request.bbox_split,
            max_features=request.max_features,
            cancel_check=cancel_event.is_set,
            progress_callback=_progress_callback,
        )

        with get_session() as session:
            job = get_job(session, job_id)
            if job is None:
                raise ValueError(f"WFS job id {job_id} does not exist.")

            output_record = create_file(
                session,
                category="data",
                path=str(output_path),
                name=output_path.name,
                format=output_path.suffix.lower().lstrip("."),
                size_bytes=output_path.stat().st_size,
                crs=str(gdf.crs) if gdf.crs else None,
            )

            create_dataset(
                session,
                file_id=output_record.id,
                geom_type=geom_type(gdf),
                feature_count=len(gdf),
                bbox=bbox_dict(gdf),
                properties_schema_json=serialize_schema(gdf),
            )

            truncated_tiles = int((collect_stats or {}).get("truncated_tiles", 0))
            api_calls = int((collect_stats or {}).get("api_calls", 0))
            if truncated_tiles > 0:
                final_progress_message = (
                    f"WFS 수집이 완료되었습니다. "
                    f"일부 영역은 최대 분할 깊이에 도달해 제한 수집되었습니다 "
                    f"(제한 타일 {truncated_tiles}개 · API 요청 {api_calls}회)."
                )
            else:
                final_progress_message = f"WFS 수집이 완료되었습니다. (API 요청 {api_calls}회)"

            update_job(
                session,
                job,
                status="succeeded",
                output_file_id=output_record.id,
                progress_percent=100,
                progress_message=final_progress_message,
            )
    except WfsCollectionCancelledError as exc:
        with get_session() as session:
            job = get_job(session, job_id)
            if job and job.status in {"queued", "running"}:
                update_job(
                    session,
                    job,
                    status="cancelled",
                    error_message=str(exc),
                    progress_message="WFS 수집이 중단되었습니다.",
                )
    except Exception as exc:
        with get_session() as session:
            job = get_job(session, job_id)
            if job and job.status in {"queued", "running"}:
                update_job(
                    session,
                    job,
                    status="failed",
                    error_message=str(exc),
                    progress_message="WFS 수집 중 오류가 발생했습니다.",
                )
