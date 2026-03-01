from __future__ import annotations

import json
import math
import shutil
import threading
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.db import get_session
from app.repositories import (
    create_job,
    dataset_feature_count_map,
    delete_file_and_related,
    get_file,
    get_job,
    list_files,
    list_jobs,
    update_job,
)
from app.services.path_service import resolve_record_path
from app.services import convert_file, ensure_storage_dirs, load_geodata, save_uploaded_file, save_uploaded_folder
from app.ui import apply_list_query, build_convert_option_items


settings = get_settings()
ensure_storage_dirs(settings.rawdata_dir, settings.data_dir)
SEOUL_TZ = ZoneInfo("Asia/Seoul")
CONVERT_INPUT_FORMATS = {"csv", "xlsx", "xls", "zip", "folder"}

app = FastAPI(title="Geodata Workbench API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONVERSION_LOCK = threading.Lock()
CONVERSION_THREADS: dict[int, threading.Thread] = {}
CONVERSION_CANCEL_EVENTS: dict[int, threading.Event] = {}
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

    if not rows:
        return pd.DataFrame(
            columns=["file_id", "id", "name", "format", "path", "abs_path", "size_bytes", "created_at"]
        )

    id_map = _category_display_ids(rows)
    records: list[dict[str, Any]] = []
    for row in rows:
        resolved_path = resolve_record_path(row.path, category_hint="rawdata")
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
            ]
        )

    raw_name_map = {row.id: row.name for row in raw_rows}
    source_name_by_output: dict[int, str] = {}
    for job in jobs:
        if job.status != "succeeded" or job.output_file_id is None:
            continue
        if job.output_file_id in source_name_by_output:
            continue
        source_name_by_output[job.output_file_id] = raw_name_map.get(job.input_file_id or -1, "")

    id_map = _category_display_ids(data_rows)
    records: list[dict[str, Any]] = []
    for row in data_rows:
        resolved_path = resolve_record_path(row.path, category_hint="data")
        source_name = source_name_by_output.get(row.id, "")
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


def _delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _delete_file(file_id: int) -> None:
    with get_session() as session:
        file_record = get_file(session, file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="삭제할 파일을 찾을 수 없습니다.")
        category_hint = "rawdata" if file_record.category == "raw" else "data"
        file_path = resolve_record_path(file_record.path, category_hint=category_hint)

    try:
        _delete_path(file_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"파일 삭제 실패: {exc}") from exc

    with get_session() as session:
        delete_file_and_related(session, file_id)


def _safe_relative_path(relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    parts = [part for part in Path(normalized).parts if part not in ("", ".", "..")]
    return Path(*parts) if parts else Path("uploaded_file")


def _group_upload_items(
    files: list[UploadFile], relative_paths: list[str], display_names: list[str]
) -> list[dict[str, Any]]:
    folders: dict[str, list[tuple[int, UploadFile, str]]] = defaultdict(list)
    singles: list[tuple[int, UploadFile, str]] = []

    for idx, upload in enumerate(files):
        raw_rel = relative_paths[idx] if idx < len(relative_paths) and relative_paths[idx] else upload.filename
        rel = _safe_relative_path(raw_rel or upload.filename or f"file_{idx}")
        if len(rel.parts) > 1:
            folder_name = rel.parts[0]
            nested = str(Path(*rel.parts[1:]))
            folders[folder_name].append((idx, upload, nested))
        else:
            singles.append((idx, upload, rel.name))

    groups: list[dict[str, Any]] = []
    for folder_name in sorted(folders):
        groups.append(
            {
                "kind": "folder",
                "name": folder_name,
                "entries": [(upload.file, nested) for _, upload, nested in folders[folder_name]],
                "count": len(folders[folder_name]),
            }
        )
    for idx, upload, rel_name in singles:
        override_name = display_names[idx].strip() if idx < len(display_names) else ""
        groups.append(
            {
                "kind": "file",
                "name": rel_name,
                "upload": upload,
                "display_name": override_name or Path(rel_name).stem,
                "count": 1,
            }
        )
    return groups


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


def _validate_upload_group(group: dict[str, Any]) -> tuple[bool, str]:
    if group["kind"] == "folder":
        rel_paths = [str(rel) for _, rel in group["entries"]]
        if _has_shapefile_bundle(rel_paths):
            return True, ""
        return False, "폴더에는 .shp/.dbf/.shx(권장 .prj) 구성 파일이 필요합니다."

    file_name = str(group["name"])
    suffix = Path(file_name).suffix.lower()
    if suffix in {".csv", ".xlsx", ".xls"}:
        return True, ""
    if suffix == ".zip":
        if _zip_has_shapefile_bundle(group["upload"]):
            return True, ""
        return False, "ZIP 내부에 .shp/.dbf/.shx(권장 .prj) 구성 파일이 필요합니다."
    return False, "직접 업로드는 csv/xlsx/xls/zip만 지원합니다."


def _conversion_params(request: ConvertRequest) -> dict[str, Any]:
    return {
        "output_format": request.output_format,
        "target_crs": request.target_crs if request.crs_handling == "transform" else None,
        "csv_lat_col": request.csv_lat_col,
        "csv_lon_col": request.csv_lon_col,
        "csv_input_crs": request.csv_input_crs,
        "crs_handling": request.crs_handling,
    }


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


def _run_conversion_job(job_id: int, request: ConvertRequest) -> None:
    cancel_event: threading.Event | None = None
    with CONVERSION_LOCK:
        cancel_event = CONVERSION_CANCEL_EVENTS.get(job_id)

    params = _conversion_params(request)
    try:
        with get_session() as session:
            convert_file(
                session,
                input_file_id=request.input_file_id,
                data_dir=settings.data_dir,
                output_format=params["output_format"],
                target_crs=params["target_crs"],
                csv_lat_col=params["csv_lat_col"],
                csv_lon_col=params["csv_lon_col"],
                csv_input_crs=params["csv_input_crs"],
                job_id=job_id,
                cancel_check=(lambda: bool(cancel_event and cancel_event.is_set())),
            )
    except Exception as exc:
        with get_session() as session:
            job = get_job(session, job_id)
            if job and job.status in {"queued", "running"}:
                update_job(session, job, status="failed", error_message=str(exc))
    finally:
        with CONVERSION_LOCK:
            CONVERSION_THREADS.pop(job_id, None)
            CONVERSION_CANCEL_EVENTS.pop(job_id, None)


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
    relative_paths: list[str] | None = Form(default=None),
    display_names: list[str] | None = Form(default=None),
) -> dict[str, Any]:
    rels = relative_paths or []
    names = display_names or []
    groups = _group_upload_items(files, rels, names)
    if not groups:
        raise HTTPException(status_code=400, detail="업로드할 파일이 없습니다.")

    errors: list[str] = []
    for group in groups:
        valid, reason = _validate_upload_group(group)
        if not valid:
            errors.append(f"{group['name']}: {reason}")
    if errors:
        raise HTTPException(status_code=400, detail={"message": "유효하지 않은 업로드 항목", "errors": errors})

    created_ids: list[int] = []
    with get_session() as session:
        for group in groups:
            if group["kind"] == "folder":
                file_id = save_uploaded_folder(
                    session,
                    folder_name=group["name"],
                    file_entries=group["entries"],
                    rawdata_dir=settings.rawdata_dir,
                )
            else:
                file_id = save_uploaded_file(
                    session,
                    uploaded_name=group["name"],
                    display_name=group["display_name"],
                    file_obj=group["upload"].file,
                    rawdata_dir=settings.rawdata_dir,
                )
            created_ids.append(int(file_id))

    return {"saved_count": len(created_ids), "file_ids": created_ids}


@app.delete("/uploads/{file_id}")
def delete_upload(file_id: int) -> dict[str, bool]:
    _delete_file(file_id)
    return {"ok": True}


@app.get("/convert/options")
def convert_options() -> dict[str, list[dict[str, Any]]]:
    raw_df = _raw_table_df()
    raw_df = raw_df[raw_df["format"].str.lower().isin(CONVERT_INPUT_FORMATS)].copy()
    items = build_convert_option_items(raw_df, settings.rawdata_dir)
    return {"items": items}


@app.get("/convert/options/{file_id}/columns")
def convert_option_columns(file_id: int) -> dict[str, Any]:
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


@app.post("/conversions")
def run_conversion(request: ConvertRequest) -> dict[str, Any]:
    params = _conversion_params(request)
    with get_session() as session:
        output_file_id = convert_file(
            session,
            input_file_id=request.input_file_id,
            data_dir=settings.data_dir,
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
    params = _conversion_params(request)
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

    cancel_event = threading.Event()
    worker = threading.Thread(
        target=_run_conversion_job,
        args=(job_id, request),
        daemon=True,
        name=f"conversion-job-{job_id}",
    )
    with CONVERSION_LOCK:
        CONVERSION_CANCEL_EVENTS[job_id] = cancel_event
        CONVERSION_THREADS[job_id] = worker
    worker.start()
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
        )


@app.post("/conversions/jobs/{job_id}/cancel")
def cancel_conversion_job(job_id: int) -> dict[str, Any]:
    with get_session() as session:
        job = get_job(session, job_id)
        if job is None or job.job_type != "convert":
            raise HTTPException(status_code=404, detail="변환 작업을 찾을 수 없습니다.")
        if job.status in {"succeeded", "failed", "cancelled"}:
            return {"ok": False, "job_id": job_id, "status": job.status}

    with CONVERSION_LOCK:
        cancel_event = CONVERSION_CANCEL_EVENTS.get(job_id)
        if cancel_event:
            cancel_event.set()

    return {"ok": True, "job_id": job_id}


@app.get("/conversions", response_model=PagedResponse)
def list_conversions(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
) -> PagedResponse:
    df = _data_table_df()
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
        df[["file_id", "name", "display_name", "total_rows", "abs_path", "crs", "format"]]
        .sort_values(by="name", ascending=True)
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
