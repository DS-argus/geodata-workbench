from __future__ import annotations

import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
import re

import geopandas as gpd
import pandas as pd
from sqlalchemy.orm import Session

from app.repositories import create_dataset, create_file, create_job, get_file, get_job, update_job
from app.services.path_service import resolve_record_path
from app.services.storage_service import allocate_output_path


SUPPORTED_VECTOR_EXTENSIONS = {".zip"}
SUPPORTED_TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls"}
SUPPORTED_OUTPUT_FORMATS = {"geoparquet", "gpkg"}


class ConversionCancelledError(RuntimeError):
    pass


def _ensure_not_cancelled(
    cancel_check: Callable[[], bool] | None,
    *,
    stage: str,
) -> None:
    if cancel_check and cancel_check():
        raise ConversionCancelledError(f"Conversion cancelled during {stage}.")


def _has_shapefile_bundle(paths: list[Path]) -> bool:
    required = {".shp", ".dbf", ".shx"}
    grouped_exts: dict[str, set[str]] = {}
    for path in paths:
        suffix = path.suffix.lower()
        if suffix not in {".shp", ".dbf", ".shx", ".prj"}:
            continue
        key = str(path.with_suffix("")).lower()
        grouped_exts.setdefault(key, set()).add(suffix)
    return any(required.issubset(exts) for exts in grouped_exts.values())


def _read_vector(input_path: Path) -> gpd.GeoDataFrame:
    if input_path.is_dir():
        shp_files = sorted(input_path.rglob("*.shp"))
        all_files = [path for path in input_path.rglob("*") if path.is_file()]
        if not _has_shapefile_bundle(all_files):
            raise ValueError("Folder must contain a shapefile bundle (.shp/.dbf/.shx).")
        if shp_files:
            return gpd.read_file(shp_files[0])

        raise ValueError("Folder does not include a supported vector dataset.")

    suffix = input_path.suffix.lower()
    if suffix == ".zip":
        with tempfile.TemporaryDirectory(prefix="gdd_zip_") as tmpdir:
            with zipfile.ZipFile(input_path, "r") as archive:
                archive.extractall(tmpdir)
            extracted_files = [path for path in Path(tmpdir).rglob("*") if path.is_file()]
            if not _has_shapefile_bundle(extracted_files):
                raise ValueError("ZIP archive must contain a shapefile bundle (.shp/.dbf/.shx).")
            shp_files = sorted(Path(tmpdir).rglob("*.shp"))
            if not shp_files:
                raise ValueError("ZIP archive does not contain a .shp file.")
            return gpd.read_file(shp_files[0])

    return gpd.read_file(input_path)


def _read_csv(
    input_path: Path,
    *,
    lat_col: str,
    lon_col: str,
    input_crs: str,
) -> gpd.GeoDataFrame:
    df = pd.read_csv(input_path)
    if lat_col not in df.columns or lon_col not in df.columns:
        raise ValueError(f"CSV must contain columns '{lat_col}' and '{lon_col}'.")

    geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
    return gpd.GeoDataFrame(df, geometry=geometry, crs=input_crs)


def _read_excel(
    input_path: Path,
    *,
    lat_col: str,
    lon_col: str,
    input_crs: str,
) -> gpd.GeoDataFrame:
    df = pd.read_excel(input_path)
    if lat_col not in df.columns or lon_col not in df.columns:
        raise ValueError(f"Excel must contain columns '{lat_col}' and '{lon_col}'.")

    geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
    return gpd.GeoDataFrame(df, geometry=geometry, crs=input_crs)


def _write_output(
    gdf: gpd.GeoDataFrame,
    *,
    input_name: str,
    output_format: str,
    data_dir: Path,
) -> Path:
    stem = _build_output_stem(input_name=input_name, crs=gdf.crs.to_string() if gdf.crs else None)
    if output_format == "geoparquet":
        output_path = allocate_output_path(data_dir, stem, "parquet")
        gdf.to_parquet(output_path, index=False)
        return output_path

    if output_format == "gpkg":
        output_path = allocate_output_path(data_dir, stem, "gpkg")
        gdf.to_file(output_path, driver="GPKG")
        return output_path

    raise ValueError(f"Unsupported output format: {output_format}")


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    slug = re.sub(r"\s+", "_", cleaned).strip("_")
    return slug or "dataset"


def _build_output_stem(*, input_name: str, crs: str | None) -> str:
    base_name = _safe_slug(Path(input_name).stem)
    crs_tag = _safe_slug(crs) if crs else "unknown_crs"
    return f"{base_name}_{crs_tag}"


def _serialize_schema(gdf: gpd.GeoDataFrame) -> dict:
    schema: dict[str, str] = {}
    for col, dtype in gdf.dtypes.items():
        if col == gdf.geometry.name:
            continue
        schema[col] = str(dtype)
    return schema


def _bbox_dict(gdf: gpd.GeoDataFrame) -> dict | None:
    if gdf.empty:
        return None
    min_x, min_y, max_x, max_y = gdf.total_bounds
    return {"min_x": float(min_x), "min_y": float(min_y), "max_x": float(max_x), "max_y": float(max_y)}


def _geom_type(gdf: gpd.GeoDataFrame) -> str | None:
    if gdf.empty:
        return None
    geom_types = sorted({str(value) for value in gdf.geom_type.dropna().unique()})
    return ",".join(geom_types) if geom_types else None


def convert_file(
    session: Session,
    *,
    input_file_id: int,
    data_dir: Path,
    output_format: str,
    target_crs: str | None = None,
    csv_lat_col: str | None = None,
    csv_lon_col: str | None = None,
    csv_input_crs: str = "EPSG:4326",
    job_id: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> int:
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(f"Output format must be one of {sorted(SUPPORTED_OUTPUT_FORMATS)}.")

    input_record = get_file(session, input_file_id)
    if input_record is None:
        raise ValueError(f"Input file id {input_file_id} does not exist.")

    input_path = resolve_record_path(input_record.path, category_hint="rawdata")
    if not input_path.exists():
        raise ValueError(f"Input file path does not exist: {input_path}")

    if job_id is None:
        job = create_job(
            session,
            job_type="convert",
            status="running",
            input_file_id=input_record.id,
            params_json={
                "output_format": output_format,
                "target_crs": target_crs,
                "csv_lat_col": csv_lat_col,
                "csv_lon_col": csv_lon_col,
                "csv_input_crs": csv_input_crs,
            },
        )
    else:
        job = get_job(session, job_id)
        if job is None:
            raise ValueError(f"Job id {job_id} does not exist.")
        job.status = "running"
        job.error_message = None
        job.finished_at = None
        session.add(job)
        session.flush()

    _ensure_not_cancelled(cancel_check, stage="startup")
    if progress_callback:
        progress_callback("Conversion job started", 5)

    try:
        suffix = input_path.suffix.lower()
        _ensure_not_cancelled(cancel_check, stage="input read")
        if progress_callback:
            progress_callback("Reading input dataset", 20)
        if suffix in SUPPORTED_TABULAR_EXTENSIONS:
            if not csv_lat_col or not csv_lon_col:
                raise ValueError("CSV/Excel conversion requires latitude and longitude column names.")
            if suffix == ".csv":
                gdf = _read_csv(
                    input_path,
                    lat_col=csv_lat_col,
                    lon_col=csv_lon_col,
                    input_crs=csv_input_crs,
                )
            else:
                gdf = _read_excel(
                    input_path,
                    lat_col=csv_lat_col,
                    lon_col=csv_lon_col,
                    input_crs=csv_input_crs,
                )
        elif input_path.is_dir() or suffix in SUPPORTED_VECTOR_EXTENSIONS:
            gdf = _read_vector(input_path)
        else:
            raise ValueError(f"Unsupported input format: {suffix}")

        _ensure_not_cancelled(cancel_check, stage="CRS preparation")
        if progress_callback:
            progress_callback("Preparing CRS transformation", 45)
        if target_crs:
            if gdf.crs is None:
                raise ValueError("Input data has no CRS. Cannot transform without source CRS.")
            gdf = gdf.to_crs(target_crs)

        _ensure_not_cancelled(cancel_check, stage="output write")
        if progress_callback:
            progress_callback("Writing converted dataset", 70)
        output_path = _write_output(
            gdf,
            input_name=input_record.name,
            output_format=output_format,
            data_dir=data_dir,
        )

        if progress_callback:
            progress_callback("Saving metadata", 85)
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
            geom_type=_geom_type(gdf),
            feature_count=len(gdf),
            bbox=_bbox_dict(gdf),
            properties_schema_json=_serialize_schema(gdf),
        )

        update_job(
            session,
            job,
            status="succeeded",
            output_file_id=output_record.id,
        )
        if progress_callback:
            progress_callback("Conversion completed", 100)
        return output_record.id
    except ConversionCancelledError as exc:
        update_job(session, job, status="cancelled", error_message=str(exc))
        raise
    except Exception as exc:
        update_job(session, job, status="failed", error_message=str(exc))
        raise
