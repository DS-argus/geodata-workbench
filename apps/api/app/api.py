from __future__ import annotations

import json
import math
import io
import shutil
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.collectors import (
    load_vworld_layer_catalog,
    save_uploaded_file,
)
from app.config import get_settings
from app.db import get_session
from app.jobs import (
    build_conversion_params,
    build_wfs_request_params,
    conversion_jobs,
    run_conversion_job,
    run_wfs_job,
    wfs_jobs,
)
from app.listing import apply_list_query, build_convert_option_items
from app.repositories import (
    create_job,
    dataset_feature_count_map,
    delete_file_and_related,
    get_file,
    get_job,
    list_files,
    list_jobs,
)
from app.services.conversion_service import convert_file
from app.services.map_service import load_geodata
from app.services.path_service import resolve_record_path
from app.services.secrets_service import VWORLD_SECRET_KEY
from app.services.secrets_service import get_secret_value, mask_secret, set_secret_value
from app.services.storage_service import ensure_storage_dirs


settings = get_settings()
SEOUL_TZ = ZoneInfo("Asia/Seoul")
CONVERT_INPUT_FORMATS = {"csv", "xlsx", "xls", "zip"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_storage_dirs(settings.rawdata_dir, settings.data_dir, settings.data_upload_dir, settings.data_wfs_dir)
    yield


app = FastAPI(title="Geodata Workbench API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TABULAR_PREVIEW_ROWS = 5
TABULAR_PROFILE_ROWS = 2000


class PagedResponse(BaseModel):
    items: list[dict[str, Any]]
    total_items: int
    total_pages: int
    page: int
    page_size: int


class ConvertRequest(BaseModel):
    input_file_id: int
    output_format: str
    crs_handling: str = "keep"
    target_crs: str | None = None
    csv_lat_col: str | None = None
    csv_lon_col: str | None = None
    csv_input_crs: str = "EPSG:4326"


class ConversionJobResponse(BaseModel):
    job_id: int


class ConversionJobStatusResponse(BaseModel):
    job_id: int
    status: str
    error_message: str | None = None
    output_file_id: int | None = None
    progress_percent: int = 0
    progress_message: str | None = None


class UploadTabularConvertRequest(BaseModel):
    output_format: str = "geoparquet"
    csv_lat_col: str
    csv_lon_col: str
    csv_input_crs: str = "EPSG:4326"


class WfsFilter(BaseModel):
    type: str
    join_with_prev: str | None = None
    column: str | None = None
    value: str | None = None
    geom_column: str | None = None
    bbox: list[float] | None = None


class WfsCollectionRequest(BaseModel):
    layer_key: str
    output_format: str = "geoparquet"
    srs_name: str = "EPSG:5186"
    filters: list[WfsFilter] | None = None
    bbox_split: int = 1
    max_features: int | None = None


class WfsJobResponse(BaseModel):
    job_id: int


class ApiKeyPayload(BaseModel):
    api_key: str


def _relative_path(path_value: str) -> str:
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(settings.project_root.resolve()))
    except Exception:
        return str(path)


def _data_display_name(path_value: str) -> str:
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(settings.data_dir.resolve()))
    except Exception:
        return path.name


def _to_kst_string(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(SEOUL_TZ).strftime("%Y-%m-%d %H:%M:%S KST")


def _category_display_ids(rows: list) -> dict[int, int]:
    ordered = sorted(rows, key=lambda row: row.created_at)
    return {row.id: index + 1 for index, row in enumerate(ordered)}


def _raw_table_df() -> pd.DataFrame:
    with get_session() as session:
        rows = list_files(session, category="raw")
        data_rows = list_files(session, category="data")
        jobs = list_jobs(session)
        feature_count_map = dataset_feature_count_map(session)

    if not rows:
        return pd.DataFrame(
            columns=[
                "file_id",
                "id",
                "name",
                "format",
                "path",
                "abs_path",
                "size_bytes",
                "created_at",
                "conversion_status",
                "conversion_output_file_id",
                "conversion_output_name",
                "conversion_output_size",
                "conversion_output_rows",
                "conversion_error",
            ]
        )

    data_name_map = {row.id: row.name for row in data_rows}
    data_size_map = {row.id: int(row.size_bytes) for row in data_rows}
    latest_job_by_input: dict[int, Any] = {}
    for job in sorted(jobs, key=lambda value: value.created_at, reverse=True):
        if job.job_type != "convert" or job.input_file_id is None:
            continue
        if job.input_file_id in latest_job_by_input:
            continue
        latest_job_by_input[job.input_file_id] = job

    id_map = _category_display_ids(rows)
    records: list[dict[str, Any]] = []
    for row in rows:
        resolved_path = resolve_record_path(row.path, category_hint="rawdata")
        latest_job = latest_job_by_input.get(row.id)
        output_file_id = int(latest_job.output_file_id) if latest_job and latest_job.output_file_id else None
        output_name = data_name_map.get(output_file_id, "") if output_file_id else ""
        output_size = data_size_map.get(output_file_id, 0) if output_file_id else 0
        output_rows = int(feature_count_map.get(output_file_id, 0)) if output_file_id else 0
        records.append(
            {
                "file_id": row.id,
                "id": id_map[row.id],
                "name": row.name,
                "format": row.format,
                "path": _relative_path(str(resolved_path)),
                "abs_path": str(resolved_path),
                "size_bytes": int(row.size_bytes),
                "created_at": _to_kst_string(row.created_at),
                "conversion_status": str(latest_job.status) if latest_job else "",
                "conversion_output_file_id": output_file_id,
                "conversion_output_name": output_name,
                "conversion_output_size": int(output_size),
                "conversion_output_rows": int(output_rows),
                "conversion_error": str(latest_job.error_message or "") if latest_job else "",
            }
        )
    return pd.DataFrame.from_records(records).sort_values(by="id", ascending=True)


def _data_table_df() -> pd.DataFrame:
    with get_session() as session:
        data_rows = list_files(session, category="data")
        raw_rows = list_files(session, category="raw")
        jobs = list_jobs(session)
        feature_count_map = dataset_feature_count_map(session)

    if not data_rows:
        return pd.DataFrame(
            columns=[
                "file_id",
                "id",
                "raw_name",
                "name",
                "format",
                "path",
                "abs_path",
                "size_bytes",
                "crs",
                "created_at",
                "total_rows",
                "display_name",
                "source_type",
                "filter_summary",
                "filter_detail_text",
            ]
        )

    raw_name_map = {row.id: row.name for row in raw_rows}
    wfs_name_map: dict[str, str] = {}
    try:
        for layer in load_vworld_layer_catalog(settings.wfs_catalog_path):
            display_name = str(layer.get("display_name") or "").strip()
            if not display_name:
                continue
            for key in (
                str(layer.get("typename") or "").strip(),
                str(layer.get("key") or "").strip(),
                display_name,
            ):
                if key:
                    wfs_name_map[key] = display_name
    except Exception:
        wfs_name_map = {}

    source_name_by_output: dict[int, str] = {}
    source_type_by_output: dict[int, str] = {}
    filter_summary_by_output: dict[int, str] = {}
    filter_detail_by_output: dict[int, str] = {}
    for job in jobs:
        if job.status != "succeeded" or job.output_file_id is None:
            continue
        if job.output_file_id in source_name_by_output:
            continue
        if job.job_type == "convert":
            source_name_by_output[job.output_file_id] = raw_name_map.get(job.input_file_id or -1, "")
            source_type_by_output[job.output_file_id] = "local_convert"
        elif job.job_type == "wfs_collect":
            params = job.params_json or {}
            layer_key = str(params.get("layer_key", "")).strip()
            source_name_by_output[job.output_file_id] = wfs_name_map.get(layer_key, layer_key)
            source_type_by_output[job.output_file_id] = "wfs"
            summary, detail = _wfs_filter_summary(params.get("filters"))
            filter_summary_by_output[job.output_file_id] = summary
            filter_detail_by_output[job.output_file_id] = detail
        else:
            source_name_by_output[job.output_file_id] = ""
            source_type_by_output[job.output_file_id] = "unknown"

    id_map = _category_display_ids(data_rows)
    records: list[dict[str, Any]] = []
    for row in data_rows:
        resolved_path = resolve_record_path(row.path, category_hint="data")
        source_name = source_name_by_output.get(row.id, "")
        source_type = source_type_by_output.get(row.id, "")
        if not source_type:
            try:
                relative = resolved_path.resolve().relative_to(settings.data_dir.resolve())
                top_folder = relative.parts[0].lower() if len(relative.parts) > 1 else ""
            except Exception:
                top_folder = ""
            if top_folder == "wfs":
                source_type = "wfs"
            elif top_folder == "upload":
                source_type = "local_convert"
            else:
                source_type = "local_convert"
        filter_summary = filter_summary_by_output.get(row.id, "")
        filter_detail = filter_detail_by_output.get(row.id, "")
        if source_type != "wfs":
            filter_summary = ""
            filter_detail = ""
        records.append(
            {
                "file_id": row.id,
                "id": id_map[row.id],
                "raw_name": source_name,
                "name": source_name if source_name else Path(row.name).stem,
                "format": row.format,
                "path": _relative_path(str(resolved_path)),
                "abs_path": str(resolved_path),
                "size_bytes": int(row.size_bytes),
                "crs": row.crs or "",
                "created_at": _to_kst_string(row.created_at),
                "total_rows": int(feature_count_map.get(row.id, 0)),
                "display_name": _data_display_name(str(resolved_path)),
                "source_type": source_type,
                "filter_summary": filter_summary,
                "filter_detail_text": filter_detail,
            }
        )
    return pd.DataFrame.from_records(records).sort_values(by="id", ascending=True)


def _repair_mojibake_text(value: str) -> str:
    if not value:
        return value

    hangul_count = sum("\uac00" <= char <= "\ud7a3" for char in value)
    if hangul_count > 0:
        return value

    if not any(ord(char) > 127 for char in value):
        return value

    for encoding in ("cp949", "euc-kr"):
        try:
            candidate = value.encode("latin1").decode(encoding)
        except Exception:
            continue
        candidate_hangul_count = sum("\uac00" <= char <= "\ud7a3" for char in candidate)
        if candidate_hangul_count > hangul_count:
            return candidate
    return value


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bytes):
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return value.decode(encoding)
            except Exception:
                continue
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return _repair_mojibake_text(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    return value


def _format_bbox_value(raw_bbox: Any) -> str:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return "BBOX"
    try:
        numbers = [float(value) for value in raw_bbox]
    except Exception:
        return "BBOX"
    return f"BBOX({numbers[0]:.5f},{numbers[1]:.5f},{numbers[2]:.5f},{numbers[3]:.5f})"


def _wfs_filter_text_list(filters: Any) -> list[str]:
    if not isinstance(filters, list):
        return []
    parts: list[str] = []
    for index, item in enumerate(filters):
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type", "")).upper()
        join = str(item.get("join_with_prev") or "AND").upper()
        join_prefix = f"{join} " if index > 0 else ""
        if ftype == "EQ":
            column = str(item.get("column") or "").strip()
            value = str(item.get("value") or "").strip()
            if column:
                parts.append(f"{join_prefix}{column} = {value}")
        elif ftype == "LIKE":
            column = str(item.get("column") or "").strip()
            value = str(item.get("value") or "").strip()
            if column and value:
                parts.append(f"{join_prefix}{column} LIKE {value}")
        elif ftype == "BBOX":
            geom_column = str(item.get("geom_column") or item.get("column") or "ag_geom")
            bbox_label = _format_bbox_value(item.get("bbox") or item.get("value"))
            parts.append(f"{join_prefix}{geom_column} {bbox_label}")
    return parts


def _wfs_filter_summary(filters: Any) -> tuple[str, str]:
    parts = _wfs_filter_text_list(filters)
    if not parts:
        return "전체", "필터 없음"
    detail = "\n".join(parts)
    if len(parts) == 1:
        summary = parts[0]
    else:
        summary = f"{parts[0]} · +{len(parts) - 1}개"
    return summary, detail


def _delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _delete_file(file_id: int) -> None:
    target_paths: list[Path] = []
    ids_to_delete: list[int] = []
    with get_session() as session:
        file_record = get_file(session, file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="삭제할 파일을 찾을 수 없습니다.")
        category_hint = "rawdata" if file_record.category == "raw" else "data"
        target_paths.append(resolve_record_path(file_record.path, category_hint=category_hint))
        ids_to_delete.append(int(file_record.id))

        if file_record.category == "raw":
            jobs = list_jobs(session)
            output_ids_linked_by_job: set[int] = set()
            for job in jobs:
                if job.input_file_id != file_id or job.output_file_id is None:
                    continue
                output_record = get_file(session, int(job.output_file_id))
                if output_record is None or output_record.category != "data":
                    continue
                output_id = int(output_record.id)
                output_ids_linked_by_job.add(output_id)
                ids_to_delete.append(output_id)
                target_paths.append(resolve_record_path(output_record.path, category_hint="data"))

    try:
        seen_paths: set[str] = set()
        for path in target_paths:
            key = str(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            _delete_path(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"파일 삭제 실패: {exc}") from exc

    with get_session() as session:
        for target_id in ids_to_delete:
            delete_file_and_related(session, target_id)


def _build_upload_items(files: list[UploadFile], display_names: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, upload in enumerate(files):
        file_name = Path(upload.filename or f"file_{idx}").name
        override_name = display_names[idx].strip() if idx < len(display_names) else ""
        items.append(
            {
                "name": file_name,
                "upload": upload,
                "display_name": override_name or Path(file_name).stem,
            }
        )
    return items


def _has_shapefile_bundle(paths: list[str]) -> bool:
    required = {".shp", ".dbf", ".shx"}
    grouped_exts: dict[str, set[str]] = {}
    for path_value in paths:
        path = Path(path_value.replace("\\", "/"))
        suffix = path.suffix.lower()
        if suffix not in {".shp", ".dbf", ".shx", ".prj"}:
            continue
        key = str(path.with_suffix(""))
        grouped_exts.setdefault(key.lower(), set()).add(suffix)
    return any(required.issubset(exts) for exts in grouped_exts.values())


def _zip_has_shapefile_bundle(upload_file: UploadFile) -> bool:
    try:
        upload_file.file.seek(0)
        with zipfile.ZipFile(upload_file.file, "r") as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
        return _has_shapefile_bundle(names)
    except Exception:
        return False
    finally:
        upload_file.file.seek(0)


def _validate_upload_item(item: dict[str, Any]) -> tuple[bool, str]:
    file_name = str(item["name"])
    suffix = Path(file_name).suffix.lower()
    if suffix == ".zip":
        if _zip_has_shapefile_bundle(item["upload"]):
            return True, ""
        return False, "ZIP 내부에 .shp/.dbf/.shx(권장 .prj) 구성 파일이 필요합니다."
    if suffix in {".csv", ".xlsx", ".xls"}:
        return False, "CSV/Excel은 컬럼 지정 팝업을 통해 업로드해 주세요."
    return False, "직접 업로드는 zip만 지원합니다."


def _read_tabular_preview(path: Path, fmt: str) -> pd.DataFrame:
    if fmt == "csv":
        last_error: Exception | None = None
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return pd.read_csv(path, nrows=TABULAR_PROFILE_ROWS, encoding=encoding, low_memory=False)
            except Exception as exc:  # pragma: no cover - fallback chain
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError("CSV 파일을 읽을 수 없습니다.")
    return pd.read_excel(path, nrows=TABULAR_PROFILE_ROWS)


def _guess_lat_lon(columns: list[str]) -> tuple[str | None, str | None]:
    lat_tokens = ("latitude", "lat", "위도")
    lon_tokens = ("longitude", "long", "lng", "lon", "경도")
    soft_lat_tokens = ("_y", " y", "(y)", " y좌표", "y좌표", "ycoord")
    soft_lon_tokens = ("_x", " x", "(x)", " x좌표", "x좌표", "xcoord")

    lowered = [col.lower() for col in columns]

    def _find(tokens: tuple[str, ...]) -> str | None:
        for token in tokens:
            for idx, col in enumerate(lowered):
                if token in col:
                    return columns[idx]
        return None

    lat = _find(lat_tokens)
    lon = _find(lon_tokens)
    if lat is None:
        lat = _find(soft_lat_tokens)
    if lon is None:
        lon = _find(soft_lon_tokens)
    return lat, lon


def _build_tabular_preview_payload(df: pd.DataFrame) -> dict[str, Any]:
    columns = [str(col) for col in df.columns]
    lat_guess, lon_guess = _guess_lat_lon(columns)

    sample = df.head(TABULAR_PREVIEW_ROWS).copy()
    for col in sample.columns:
        sample[col] = sample[col].map(_normalize_value)

    numeric_ranges: dict[str, dict[str, float | int]] = {}
    for col in columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        valid = numeric.dropna()
        if valid.empty:
            continue
        numeric_ranges[col] = {
            "min": float(valid.min()),
            "max": float(valid.max()),
            "count": int(valid.shape[0]),
        }

    return {
        "columns": columns,
        "sample_rows": sample.to_dict("records"),
        "numeric_ranges": numeric_ranges,
        "suggested_lat": lat_guess,
        "suggested_lon": lon_guess,
        "lat_reference": {"min": -90, "max": 90},
        "lon_reference": {"min": -180, "max": 180},
    }


def _read_tabular_preview_from_upload(upload_file: UploadFile, fmt: str) -> pd.DataFrame:
    upload_file.file.seek(0)
    raw = upload_file.file.read()
    upload_file.file.seek(0)
    if fmt == "csv":
        last_error: Exception | None = None
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return pd.read_csv(io.BytesIO(raw), nrows=TABULAR_PROFILE_ROWS, encoding=encoding, low_memory=False)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError("CSV 파일을 읽을 수 없습니다.")
    return pd.read_excel(io.BytesIO(raw), nrows=TABULAR_PROFILE_ROWS)


def _friendly_upload_error(message: str) -> str:
    text = (message or "").strip()
    lowered = text.lower()
    if "shapefile bundle" in lowered or ".shp/.dbf/.shx" in lowered:
        return "Shapefile 구성 파일(.shp/.dbf/.shx)을 확인해 주세요."
    if "has no crs" in lowered or "no crs" in lowered:
        return "입력 데이터에 CRS 정보가 없어 변환할 수 없습니다."
    if "latitude and longitude column names" in lowered:
        return "위도/경도 컬럼을 선택해 주세요."
    if "unsupported input format" in lowered:
        return "지원하지 않는 입력 형식입니다."
    if "not exist" in lowered:
        return "입력 파일을 찾을 수 없습니다."
    return text or "업로드 처리 중 오류가 발생했습니다."


def _tabular_preview_payload(file_id: int) -> dict[str, Any]:
    with get_session() as session:
        file_record = get_file(session, file_id)
        if file_record is None or file_record.category != "raw":
            raise HTTPException(status_code=404, detail="입력 파일을 찾을 수 없습니다.")
        fmt = (file_record.format or "").lower()
        if fmt not in {"csv", "xlsx", "xls"}:
            raise HTTPException(status_code=400, detail="CSV/Excel 파일에서만 컬럼 정보를 조회할 수 있습니다.")
        input_path = resolve_record_path(file_record.path, category_hint="rawdata")

    if not input_path.exists():
        raise HTTPException(status_code=404, detail="입력 파일 경로를 찾을 수 없습니다.")

    try:
        df = _read_tabular_preview(input_path, fmt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"파일 컬럼 조회 실패: {exc}") from exc

    return _build_tabular_preview_payload(df)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/uploads", response_model=PagedResponse)
def list_uploads(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
) -> PagedResponse:
    df = _raw_table_df()
    page_df, total_items, total_pages = apply_list_query(
        df,
        query=query,
        format_filter=None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return PagedResponse(
        items=page_df.to_dict("records"),
        total_items=total_items,
        total_pages=total_pages,
        page=page,
        page_size=page_size,
    )


@app.post("/uploads")
async def create_uploads(
    files: list[UploadFile] = File(...),
    display_names: list[str] | None = Form(default=None),
    output_format: str = Form(default="geoparquet"),
) -> dict[str, Any]:
    if output_format not in {"geoparquet", "gpkg"}:
        raise HTTPException(status_code=400, detail="출력 형식은 geoparquet 또는 gpkg 이어야 합니다.")

    names = display_names or []
    items = _build_upload_items(files, names)
    if not items:
        raise HTTPException(status_code=400, detail="업로드할 파일이 없습니다.")

    errors: list[str] = []
    for item in items:
        valid, reason = _validate_upload_item(item)
        if not valid:
            errors.append(f"{item['name']}: {reason}")
    if errors:
        raise HTTPException(status_code=400, detail={"message": "유효하지 않은 업로드 항목", "errors": errors})

    created_ids: list[int] = []
    success_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    for item in items:
        raw_path_for_cleanup: Path | None = None
        raw_id_for_cleanup: int | None = None
        item_name = str(item.get("display_name") or item["name"])
        try:
            with get_session() as session:
                file_id = save_uploaded_file(
                    session,
                    uploaded_name=item["name"],
                    display_name=item["display_name"],
                    file_obj=item["upload"].file,
                    rawdata_dir=settings.rawdata_dir,
                )

                raw_id_for_cleanup = int(file_id)
                raw_record = get_file(session, int(file_id))
                if raw_record:
                    raw_path_for_cleanup = resolve_record_path(raw_record.path, category_hint="rawdata")

                try:
                    output_file_id = convert_file(
                        session,
                        input_file_id=int(file_id),
                        data_dir=settings.data_upload_dir,
                        output_format=output_format,
                    )
                except Exception:
                    # Trigger transaction rollback first; filesystem cleanup is handled below.
                    raise

            created_ids.append(int(raw_id_for_cleanup))
            success_items.append(
                {
                    "file_id": int(raw_id_for_cleanup),
                    "output_file_id": int(output_file_id),
                    "name": item_name,
                }
            )
        except Exception as exc:
            # Atomic behavior: if conversion fails, remove the raw file too.
            if raw_path_for_cleanup is not None:
                try:
                    _delete_path(raw_path_for_cleanup)
                except Exception:
                    pass
            if raw_id_for_cleanup is not None:
                try:
                    with get_session() as session:
                        delete_file_and_related(session, raw_id_for_cleanup)
                except Exception:
                    pass
            failed_items.append(
                {
                    "name": item_name,
                    "message": str(exc),
                    "user_message": _friendly_upload_error(str(exc)),
                }
            )

    return {
        "saved_count": len(created_ids),
        "file_ids": created_ids,
        "success_items": success_items,
        "failed_items": failed_items,
    }


@app.delete("/uploads/{file_id}")
def delete_upload(file_id: int) -> dict[str, bool]:
    _delete_file(file_id)
    return {"ok": True}


@app.post("/uploads/tabular/inspect")
async def inspect_tabular_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(str(file.filename or "")).suffix.lower().lstrip(".")
    if suffix not in {"csv", "xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="CSV/Excel 파일만 미리보기를 지원합니다.")
    try:
        df = _read_tabular_preview_from_upload(file, suffix)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_upload_error(str(exc))) from exc
    return _build_tabular_preview_payload(df)


@app.post("/uploads/tabular/submit")
async def submit_tabular_upload(
    file: UploadFile = File(...),
    display_name: str = Form(default=""),
    output_format: str = Form(default="geoparquet"),
    csv_lat_col: str = Form(...),
    csv_lon_col: str = Form(...),
    csv_input_crs: str = Form(default="EPSG:4326"),
) -> dict[str, Any]:
    suffix = Path(str(file.filename or "")).suffix.lower().lstrip(".")
    if suffix not in {"csv", "xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="CSV/Excel 파일만 지원합니다.")
    if output_format not in {"geoparquet", "gpkg"}:
        raise HTTPException(status_code=400, detail="출력 형식은 geoparquet 또는 gpkg 이어야 합니다.")
    if csv_input_crs.strip().upper() != "EPSG:4326":
        raise HTTPException(status_code=400, detail="CSV/Excel 입력 CRS는 EPSG:4326만 지원합니다.")

    file_id: int | None = None
    raw_path_for_cleanup: Path | None = None
    try:
        with get_session() as session:
            file_id = save_uploaded_file(
                session,
                uploaded_name=str(file.filename or "uploaded.csv"),
                display_name=display_name.strip() or Path(str(file.filename or "uploaded.csv")).stem,
                file_obj=file.file,
                rawdata_dir=settings.rawdata_dir,
            )
            raw_record = get_file(session, int(file_id))
            if raw_record:
                raw_path_for_cleanup = resolve_record_path(raw_record.path, category_hint="rawdata")
            output_file_id = convert_file(
                session,
                input_file_id=int(file_id),
                data_dir=settings.data_upload_dir,
                output_format=output_format,
                csv_lat_col=csv_lat_col,
                csv_lon_col=csv_lon_col,
                csv_input_crs="EPSG:4326",
            )
    except Exception as exc:
        if raw_path_for_cleanup is not None:
            try:
                _delete_path(raw_path_for_cleanup)
            except Exception:
                pass
        if file_id is not None:
            try:
                with get_session() as session:
                    delete_file_and_related(session, int(file_id))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=_friendly_upload_error(str(exc))) from exc

    data_df = _data_table_df()
    row = data_df.loc[data_df["file_id"] == int(output_file_id)]
    output = row.iloc[0].to_dict() if not row.empty else {"file_id": output_file_id}
    return {"ok": True, "file_id": int(file_id), "output": output}


@app.get("/uploads/{file_id}/tabular-preview")
def upload_tabular_preview(file_id: int) -> dict[str, Any]:
    return _tabular_preview_payload(file_id)


@app.post("/uploads/{file_id}/convert")
def convert_uploaded_tabular(file_id: int, request: UploadTabularConvertRequest) -> dict[str, Any]:
    if request.output_format not in {"geoparquet", "gpkg"}:
        raise HTTPException(status_code=400, detail="출력 형식은 geoparquet 또는 gpkg 이어야 합니다.")

    with get_session() as session:
        raw_file = get_file(session, file_id)
        if raw_file is None or raw_file.category != "raw":
            raise HTTPException(status_code=404, detail="입력 파일을 찾을 수 없습니다.")
        if (raw_file.format or "").lower() not in {"csv", "xlsx", "xls"}:
            raise HTTPException(status_code=400, detail="CSV/Excel 파일만 컬럼 지정 변환을 지원합니다.")
        output_file_id = convert_file(
            session,
            input_file_id=file_id,
            data_dir=settings.data_upload_dir,
            output_format=request.output_format,
            csv_lat_col=request.csv_lat_col,
            csv_lon_col=request.csv_lon_col,
            csv_input_crs=request.csv_input_crs,
        )

    data_df = _data_table_df()
    row = data_df.loc[data_df["file_id"] == int(output_file_id)]
    output = row.iloc[0].to_dict() if not row.empty else {"file_id": output_file_id}
    return {"ok": True, "output": output}


@app.get("/convert/options")
def convert_options() -> dict[str, list[dict[str, Any]]]:
    raw_df = _raw_table_df()
    raw_df = raw_df[raw_df["format"].str.lower().isin(CONVERT_INPUT_FORMATS)].copy()
    items = build_convert_option_items(raw_df, settings.rawdata_dir)
    return {"items": items}


@app.get("/convert/options/{file_id}/columns")
def convert_option_columns(file_id: int) -> dict[str, Any]:
    return _tabular_preview_payload(file_id)


@app.post("/conversions")
def run_conversion(request: ConvertRequest) -> dict[str, Any]:
    params = build_conversion_params(request)
    with get_session() as session:
        output_file_id = convert_file(
            session,
            input_file_id=request.input_file_id,
            data_dir=settings.data_upload_dir,
            output_format=params["output_format"],
            target_crs=params["target_crs"],
            csv_lat_col=params["csv_lat_col"],
            csv_lon_col=params["csv_lon_col"],
            csv_input_crs=params["csv_input_crs"],
        )

    data_df = _data_table_df()
    row = data_df.loc[data_df["file_id"] == int(output_file_id)]
    output = row.iloc[0].to_dict() if not row.empty else {"file_id": output_file_id}
    return {"ok": True, "output": output}


@app.post("/conversions/start", response_model=ConversionJobResponse)
def start_conversion(request: ConvertRequest) -> ConversionJobResponse:
    params = build_conversion_params(request)
    with get_session() as session:
        input_file = get_file(session, request.input_file_id)
        if input_file is None:
            raise HTTPException(status_code=400, detail="입력 파일을 찾을 수 없습니다.")
        job = create_job(
            session,
            job_type="convert",
            status="queued",
            input_file_id=request.input_file_id,
            params_json=params,
        )
        job_id = int(job.id)

    conversion_jobs.start(job_id, run_conversion_job, request)
    return ConversionJobResponse(job_id=job_id)


@app.get("/conversions/jobs/{job_id}", response_model=ConversionJobStatusResponse)
def conversion_job_status(job_id: int) -> ConversionJobStatusResponse:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None or job.job_type != "convert":
            raise HTTPException(status_code=404, detail="변환 작업을 찾을 수 없습니다.")
        return ConversionJobStatusResponse(
            job_id=int(job.id),
            status=str(job.status),
            error_message=job.error_message,
            output_file_id=job.output_file_id,
            progress_percent=int(getattr(job, "progress_percent", 0) or 0),
            progress_message=getattr(job, "progress_message", None),
        )


@app.post("/conversions/jobs/{job_id}/cancel")
def cancel_conversion_job(job_id: int) -> dict[str, Any]:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None or job.job_type != "convert":
            raise HTTPException(status_code=404, detail="변환 작업을 찾을 수 없습니다.")
        if job.status in {"succeeded", "failed", "cancelled"}:
            return {"ok": False, "job_id": job_id, "status": job.status}

    conversion_jobs.cancel(job_id)
    return {"ok": True, "job_id": job_id}


@app.get("/wfs/config")
def wfs_config() -> dict[str, Any]:
    with get_session() as session:
        persisted_key = get_secret_value(session, VWORLD_SECRET_KEY)
    key = settings.vworld_api_key or persisted_key
    return {
        "provider": "vworld",
        "has_api_key": bool(key),
        "key_masked": mask_secret(key),
    }


@app.put("/wfs/config/api-key")
def set_wfs_api_key(payload: ApiKeyPayload) -> dict[str, Any]:
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키를 입력해 주세요.")
    with get_session() as session:
        set_secret_value(session, key=VWORLD_SECRET_KEY, value=api_key)
    return {"ok": True, "key_masked": mask_secret(api_key)}


@app.get("/wfs/layers")
def list_wfs_layers() -> dict[str, Any]:
    try:
        items = load_vworld_layer_catalog(settings.wfs_catalog_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WFS 레이어 정보를 불러오지 못했습니다: {exc}") from exc
    return {"items": items}


@app.post("/wfs/collections/start", response_model=WfsJobResponse)
def start_wfs_collection(request: WfsCollectionRequest) -> WfsJobResponse:
    params = build_wfs_request_params(request)
    with get_session() as session:
        key = settings.vworld_api_key or get_secret_value(session, VWORLD_SECRET_KEY)
        if not key:
            raise HTTPException(status_code=400, detail="VWorld API 키가 없습니다. WFS 설정에서 먼저 입력해 주세요.")
        job = create_job(
            session,
            job_type="wfs_collect",
            status="queued",
            input_file_id=None,
            params_json=params,
        )
        job_id = int(job.id)

    wfs_jobs.start(job_id, run_wfs_job, request)
    return WfsJobResponse(job_id=job_id)


@app.get("/wfs/jobs/{job_id}", response_model=ConversionJobStatusResponse)
def wfs_job_status(job_id: int) -> ConversionJobStatusResponse:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None or job.job_type != "wfs_collect":
            raise HTTPException(status_code=404, detail="WFS 수집 작업을 찾을 수 없습니다.")
        return ConversionJobStatusResponse(
            job_id=int(job.id),
            status=str(job.status),
            error_message=job.error_message,
            output_file_id=job.output_file_id,
            progress_percent=int(getattr(job, "progress_percent", 0) or 0),
            progress_message=getattr(job, "progress_message", None),
        )


@app.post("/wfs/jobs/{job_id}/cancel")
def cancel_wfs_job(job_id: int) -> dict[str, Any]:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None or job.job_type != "wfs_collect":
            raise HTTPException(status_code=404, detail="WFS 수집 작업을 찾을 수 없습니다.")
        if job.status in {"succeeded", "failed", "cancelled"}:
            return {"ok": False, "job_id": job_id, "status": job.status}

    wfs_jobs.cancel(job_id)
    return {"ok": True, "job_id": job_id}


@app.get("/wfs/collections", response_model=PagedResponse)
def list_wfs_collections(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
) -> PagedResponse:
    df = _data_table_df()
    df = df[df["source_type"] == "wfs"].copy()
    page_df, total_items, total_pages = apply_list_query(
        df,
        query=query,
        format_filter=None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return PagedResponse(
        items=page_df.to_dict("records"),
        total_items=total_items,
        total_pages=total_pages,
        page=page,
        page_size=page_size,
    )


@app.delete("/wfs/collections/{file_id}")
def delete_wfs_collection(file_id: int) -> dict[str, bool]:
    _delete_file(file_id)
    return {"ok": True}


@app.get("/conversions", response_model=PagedResponse)
def list_conversions(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
) -> PagedResponse:
    df = _data_table_df()
    df = df[df["source_type"] == "local_convert"].copy()
    page_df, total_items, total_pages = apply_list_query(
        df,
        query=query,
        format_filter=None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return PagedResponse(
        items=page_df.to_dict("records"),
        total_items=total_items,
        total_pages=total_pages,
        page=page,
        page_size=page_size,
    )


@app.delete("/conversions/{file_id}")
def delete_conversion(file_id: int) -> dict[str, bool]:
    _delete_file(file_id)
    return {"ok": True}


@app.get("/datasets")
def list_datasets() -> dict[str, list[dict[str, Any]]]:
    df = _data_table_df()
    items = (
        df[["file_id", "name", "display_name", "total_rows", "abs_path", "crs", "format", "source_type"]]
        .sort_values(by=["source_type", "name"], ascending=[True, True])
        .to_dict("records")
    )
    return {"items": items}


@app.get("/datasets/{file_id}/preview")
def dataset_preview(file_id: int, limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    df = _data_table_df()
    selected = df.loc[df["file_id"] == file_id]
    if selected.empty:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")

    path = Path(str(selected.iloc[0]["abs_path"]))
    gdf = load_geodata(path)
    data_df = gdf.drop(columns=gdf.geometry.name, errors="ignore")
    preview = data_df.head(limit).copy()
    for col in preview.columns:
        preview[col] = preview[col].map(_normalize_value)
    return {"columns": [str(c) for c in preview.columns], "rows": preview.to_dict("records")}


@app.get("/datasets/{file_id}/geojson")
def dataset_geojson(file_id: int, limit: int = Query(default=1000, ge=1, le=20000)) -> JSONResponse:
    df = _data_table_df()
    selected = df.loc[df["file_id"] == file_id]
    if selected.empty:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")

    path = Path(str(selected.iloc[0]["abs_path"]))
    gdf = load_geodata(path)
    if len(gdf) > limit:
        gdf = gdf.sample(n=limit, random_state=42).copy()

    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        if str(gdf[col].dtype) == "object":
            gdf[col] = gdf[col].map(_normalize_value)

    return JSONResponse(content=json.loads(gdf.to_json()))
