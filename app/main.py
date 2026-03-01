from __future__ import annotations

import shutil
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session
from app.repositories import dataset_feature_count_map, delete_file_and_related, list_files, list_jobs
from app.services import (
    build_map,
    convert_file,
    ensure_storage_dirs,
    load_geodata,
    save_uploaded_file,
    save_uploaded_folder,
)
from app.ui import apply_list_query, build_convert_option_items
from streamlit_folium import st_folium


settings = get_settings()
ensure_storage_dirs(settings.rawdata_dir, settings.data_dir)
CONVERT_INPUT_FORMATS = {"csv", "xlsx", "xls", "zip", "folder"}
SEOUL_TZ = ZoneInfo("Asia/Seoul")
CRS_PRESETS = [
    ("EPSG:4326", "WGS 84", "GPS/웹 API 표준 좌표계, 경위도(도 단위)"),
    ("EPSG:3857", "Web Mercator", "대부분의 웹지도 타일에서 사용하는 투영 좌표계"),
    ("EPSG:5179", "Korea 2000 / Unified CS", "국내 공간분석에서 자주 쓰는 미터 단위 좌표계"),
    ("EPSG:5186", "Korea 2000 / Central Belt", "국토정보 데이터에서 자주 보이는 중부원점 좌표계"),
    ("EPSG:32652", "UTM Zone 52N", "동아시아 북반구 UTM 기반 분석 좌표계"),
]


st.set_page_config(page_title="Geodata Dashboard", layout="wide")
st.title("Geodata Dashboard")
st.caption("Upload raw geodata, convert to standard formats, and validate quickly on a map.")


def _check_db() -> str | None:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return None
    except Exception as exc:  # pragma: no cover - streamlit runtime branch
        return str(exc)


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


def _to_display_time(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(SEOUL_TZ).strftime("%Y-%m-%d %H:%M:%S KST")


def _category_display_ids(rows: list) -> dict[int, int]:
    ordered = sorted(rows, key=lambda row: row.created_at)
    return {row.id: index + 1 for index, row in enumerate(ordered)}


def _raw_table() -> pd.DataFrame:
    with get_session() as session:
        rows = list_files(session, category="raw")

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
                "crs",
                "created_at",
            ]
        )

    id_map = _category_display_ids(rows)
    records = []
    for row in rows:
        records.append(
            {
                "file_id": row.id,
                "id": id_map[row.id],
                "name": row.name,
                "format": row.format,
                "path": _relative_path(row.path),
                "abs_path": row.path,
                "size_bytes": int(row.size_bytes),
                "crs": row.crs or "",
                "created_at": _to_display_time(row.created_at),
            }
        )
    return pd.DataFrame.from_records(records).sort_values(by="id", ascending=True)


def _data_table() -> pd.DataFrame:
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
    records = []
    for row in data_rows:
        records.append(
            {
                "file_id": row.id,
                "id": id_map[row.id],
                "raw_name": source_name_by_output.get(row.id, ""),
                "name": source_name_by_output.get(row.id, Path(row.name).stem),
                "format": row.format,
                "path": _relative_path(row.path),
                "abs_path": row.path,
                "size_bytes": int(row.size_bytes),
                "crs": row.crs or "",
                "created_at": _to_display_time(row.created_at),
                "total_rows": int(feature_count_map.get(row.id, 0)),
            }
        )
    return pd.DataFrame.from_records(records).sort_values(by="id", ascending=True)


def _tabular_columns(path: Path) -> list[str]:
    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path, nrows=0)
        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(path, nrows=0)
        else:
            return []
        return list(df.columns)
    except Exception:
        return []


def _group_uploads(uploaded_files: list) -> list[dict]:
    folders: dict[str, list] = defaultdict(list)
    files: list = []

    for uploaded in uploaded_files:
        path = Path(uploaded.name.replace("\\", "/"))
        if len(path.parts) > 1:
            folder_name = path.parts[0]
            relative_path = str(Path(*path.parts[1:]))
            folders[folder_name].append((uploaded, relative_path))
        else:
            files.append(uploaded)

    groups: list[dict] = []
    for folder_name in sorted(folders):
        groups.append(
            {
                "kind": "folder",
                "name": folder_name,
                "entries": folders[folder_name],
                "count": len(folders[folder_name]),
            }
        )
    for uploaded in files:
        groups.append(
            {
                "kind": "file",
                "name": uploaded.name,
                "uploaded": uploaded,
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
        base_key = str(path.with_suffix("")).lower()
        grouped_exts.setdefault(base_key, set()).add(suffix)

    return any(required.issubset(exts) for exts in grouped_exts.values())


def _zip_has_shapefile_bundle(uploaded_file) -> bool:
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file, "r") as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
        return _has_shapefile_bundle(names)
    except Exception:
        return False
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass


def _validate_upload_group(group: dict) -> tuple[bool, str]:
    if group["kind"] == "folder":
        relative_paths = [str(relative_path) for _, relative_path in group["entries"]]
        if _has_shapefile_bundle(relative_paths):
            return True, ""
        return (
            False,
            "폴더에는 같은 데이터셋 기준 .shp/.dbf/.shx(권장 .prj) 구성 파일이 포함되어야 합니다.",
        )

    file_name = str(group["name"])
    suffix = Path(file_name).suffix.lower()
    if suffix in {".csv", ".xlsx", ".xls"}:
        return True, ""
    if suffix == ".zip":
        if _zip_has_shapefile_bundle(group["uploaded"]):
            return True, ""
        return (
            False,
            "ZIP 내부에 같은 데이터셋 기준 .shp/.dbf/.shx(권장 .prj) 구성 파일이 필요합니다.",
        )
    return (
        False,
        "직접 업로드는 csv/xlsx/xls/zip만 지원합니다. 공간데이터는 폴더 또는 ZIP으로 업로드하세요.",
    )


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


def _normalize_preview_value(value):
    if isinstance(value, bytes):
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return value.decode(encoding)
            except Exception:
                continue
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return _repair_mojibake_text(value)
    return value


def _preview_dataframe(gdf: pd.DataFrame, max_rows: int = 10) -> pd.DataFrame:
    preview = gdf.head(max_rows).copy()
    object_columns = preview.select_dtypes(include=["object"]).columns
    for column in object_columns:
        preview[column] = preview[column].map(_normalize_preview_value)
    return preview


@st.cache_data(show_spinner=False)
def _cached_geodata(path: str, mtime_ns: int):
    del mtime_ns
    return load_geodata(path)


def _render_crs_preset_dialog(*, state_key: str = "target_crs") -> None:
    @st.dialog("CRS 목록", width="medium")
    def _dialog() -> None:
        st.caption("자주 사용하는 좌표계")
        for code, title, desc in CRS_PRESETS:
            info_col, action_col = st.columns([3, 1], vertical_alignment="center")
            with info_col:
                st.markdown(f"**{code} · {title}**")
                st.caption(desc)
            with action_col:
                if st.button("선택", key=f"{state_key}_preset_{code}", width="stretch"):
                    st.session_state[state_key] = code
                    st.session_state["open_crs_dialog"] = False
                    st.rerun()

    _dialog()


def _delete_file(file_id: int) -> tuple[bool, str]:
    try:
        with get_session() as session:
            file_path = delete_file_and_related(session, file_id)

        if not file_path:
            return False, "삭제할 파일을 찾을 수 없습니다."

        path = Path(file_path)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

        return True, "삭제되었습니다."
    except Exception as exc:
        return False, f"삭제 실패: {exc}"


def _size_mb_label(size_bytes: int) -> str:
    return f"{(int(size_bytes) / (1024 * 1024)):.2f} MB"


def _list_view_controls(df: pd.DataFrame, *, state_key: str) -> tuple[pd.DataFrame, int, int]:
    page_size = 20
    available_formats = sorted(df["format"].dropna().astype(str).unique().tolist()) if "format" in df.columns else []

    c1, c2, c3, c4 = st.columns([2.2, 1.4, 1.2, 1.2])
    query = c1.text_input(
        "검색",
        key=f"{state_key}_query",
        placeholder="name/path LIKE 검색 (예: road%, %road%)",
    )
    format_filter = c2.multiselect("포맷", available_formats, key=f"{state_key}_formats")
    sort_by = c3.selectbox("정렬 기준", ["created_at", "id", "name", "size_bytes"], key=f"{state_key}_sort_by")
    sort_dir = c4.selectbox("정렬 방향", ["desc", "asc"], key=f"{state_key}_sort_dir")

    controls_signature = (query, tuple(format_filter), sort_by, sort_dir)
    signature_key = f"{state_key}_signature"
    if st.session_state.get(signature_key) != controls_signature:
        st.session_state[signature_key] = controls_signature
        st.session_state[f"{state_key}_page"] = 1

    page = int(st.session_state.get(f"{state_key}_page", 1))
    page_df, total_items, total_pages = apply_list_query(
        df,
        query=query,
        format_filter=format_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )

    nav_left, nav_mid, nav_right = st.columns([1.2, 2.2, 1.2])
    if nav_left.button("◀ 이전", key=f"{state_key}_prev", disabled=page <= 1):
        st.session_state[f"{state_key}_page"] = page - 1
        st.rerun()
    nav_mid.markdown(
        (
            "<div style='text-align:center; color:#777; margin-top:0.45rem;'>"
            f"총 {total_items}건 · {page}/{total_pages} 페이지"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if nav_right.button("다음 ▶", key=f"{state_key}_next", disabled=page >= total_pages):
        st.session_state[f"{state_key}_page"] = page + 1
        st.rerun()

    return page_df, total_items, total_pages


def _render_file_table(
    title: str,
    df: pd.DataFrame,
    *,
    table_key: str,
    active_tab_on_rerun: str,
    include_crs: bool = False,
) -> None:
    st.markdown(f"### {title}")

    if df.empty:
        st.info("항목이 없습니다.")
        return

    page_df, _, _ = _list_view_controls(df, state_key=f"{table_key}_list")

    st.markdown(
        """
        <style>
          .row-header { color: #777; font-size: 0.82rem; margin-bottom: 0.25rem; }
          .row-cell {
            display: flex;
            align-items: center;
            min-height: 2.1rem;
            white-space: nowrap;
            overflow-x: auto;
            font-size: 0.95rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_widths = [0.7, 0.7, 2.6, 1.4, 2.0, 3.4, 1.6] if include_crs else [0.7, 0.7, 2.6, 1.4, 2.0, 4.0]
    header_cols = st.columns(col_widths)
    header_cols[0].markdown('<div class="row-header">삭제</div>', unsafe_allow_html=True)
    header_cols[1].markdown('<div class="row-header">id</div>', unsafe_allow_html=True)
    header_cols[2].markdown('<div class="row-header">name</div>', unsafe_allow_html=True)
    header_cols[3].markdown('<div class="row-header">size_bytes</div>', unsafe_allow_html=True)
    header_cols[4].markdown('<div class="row-header">created_at</div>', unsafe_allow_html=True)
    header_cols[5].markdown('<div class="row-header">path</div>', unsafe_allow_html=True)
    if include_crs:
        header_cols[6].markdown('<div class="row-header">crs</div>', unsafe_allow_html=True)

    for row in page_df.to_dict("records"):
        with st.container(border=True):
            row_cols = st.columns(col_widths)
            if row_cols[0].button("🗑️", key=f"{table_key}_delete_{row['file_id']}"):
                ok, message = _delete_file(int(row["file_id"]))
                if ok:
                    st.session_state["flash_message"] = message
                    st.session_state["force_tab"] = active_tab_on_rerun
                    st.rerun()
                st.error(message)
            row_cols[1].markdown(f'<div class="row-cell">{row["id"]}</div>', unsafe_allow_html=True)
            row_cols[2].markdown(f'<div class="row-cell"><b>{row["name"]}</b></div>', unsafe_allow_html=True)
            row_cols[3].markdown(f'<div class="row-cell">{_size_mb_label(row["size_bytes"])}</div>', unsafe_allow_html=True)
            row_cols[4].markdown(
                f'<div class="row-cell">{row["created_at"]}</div>',
                unsafe_allow_html=True,
            )
            row_cols[5].markdown(f'<div class="row-cell">{row["path"]}</div>', unsafe_allow_html=True)
            if include_crs:
                row_cols[6].markdown(
                    f'<div class="row-cell">{row.get("crs") or "-"}</div>',
                    unsafe_allow_html=True,
                )


if "flash_message" in st.session_state:
    st.success(st.session_state.pop("flash_message"))

db_error = _check_db()
if db_error:
    st.error("Database connection failed. Start PostgreSQL/PostGIS and check DATABASE_URL.")
    st.code(db_error)
    st.stop()


tab_labels = ["Upload", "Convert", "Browse & Map"]
force_tab = st.session_state.pop("force_tab", None)
if force_tab in tab_labels:
    tab_upload, tab_convert, tab_browse = st.tabs(tab_labels, default=force_tab)
else:
    tab_upload, tab_convert, tab_browse = st.tabs(tab_labels)

with tab_upload:
    st.subheader("Upload raw datasets")
    st.markdown(
        """
        <style>
          .stFileUploader [data-testid="stFileUploaderFile"] { display: none !important; }
          .stFileUploader [data-testid="stFileUploaderPagination"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    upload_col, save_col = st.columns([5, 1], vertical_alignment="bottom")
    with upload_col:
        uploaded_files = st.file_uploader(
            "Upload files or a folder (directory upload)",
            accept_multiple_files="directory",
            type=None,
            help=(
                "공간데이터는 구성 파일(.shp/.dbf/.shx) 포함 폴더/ZIP으로 업로드하세요. "
                "CSV/Excel은 직접 드래그앤드롭으로 업로드하세요."
            ),
        )
    with save_col:
        save_uploads_clicked = st.button("Save uploads", type="primary", width="stretch")

    upload_groups: list[dict] = []
    custom_names: dict[str, str] = {}
    if uploaded_files:
        upload_groups = _group_uploads(uploaded_files)
        folder_count = sum(1 for group in upload_groups if group["kind"] == "folder")
        file_count = sum(1 for group in upload_groups if group["kind"] == "file")
        st.caption(f"선택됨: 폴더 {folder_count}개 / 파일 {file_count}개")
        if file_count:
            st.markdown("#### 파일 이름 설정")
            for group in upload_groups:
                if group["kind"] != "file":
                    continue
                name_key = f"upload_name_{group['name']}_{group['uploaded'].size}"
                default_name = Path(group["name"]).stem
                custom_names[name_key] = st.text_input(
                    f"{group['name']} 이름",
                    value=st.session_state.get(name_key, default_name),
                    key=name_key,
                ).strip() or default_name

    if save_uploads_clicked:
        if not uploaded_files:
            st.warning("Please upload at least one file.")
        else:
            validation_errors: list[str] = []
            for group in upload_groups:
                is_valid, reason = _validate_upload_group(group)
                if not is_valid:
                    validation_errors.append(f"{group['name']}: {reason}")

            if validation_errors:
                st.error("지원하지 않는 업로드 항목이 있습니다.")
                for message in validation_errors:
                    st.caption(f"- {message}")
            else:
                saved_ids: list[int] = []
                upload_progress = st.progress(0, text="Saving uploaded files...")
                with get_session() as session:
                    total_groups = len(upload_groups)
                    for index, group in enumerate(upload_groups, start=1):
                        if group["kind"] == "folder":
                            file_id = save_uploaded_folder(
                                session,
                                folder_name=group["name"],
                                file_entries=group["entries"],
                                rawdata_dir=settings.rawdata_dir,
                            )
                            progress_text = f"Saved folder {index}/{total_groups}: {group['name']}"
                        else:
                            uploaded = group["uploaded"]
                            name_key = f"upload_name_{group['name']}_{uploaded.size}"
                            file_id = save_uploaded_file(
                                session,
                                uploaded_name=group["name"],
                                display_name=custom_names.get(name_key, Path(group["name"]).stem),
                                file_obj=uploaded,
                                rawdata_dir=settings.rawdata_dir,
                            )
                            progress_text = f"Saved file {index}/{total_groups}: {group['name']}"
                        saved_ids.append(file_id)
                        upload_progress.progress(
                            int((index / total_groups) * 100),
                            text=progress_text,
                        )
                upload_progress.empty()
                st.success(f"Saved {len(saved_ids)} item(s).")

    raw_df = _raw_table()
    _render_file_table(
        "업로드 목록",
        raw_df,
        table_key="raw_table",
        active_tab_on_rerun="Upload",
    )

with tab_convert:
    st.subheader("Convert raw dataset")

    raw_df = _raw_table()
    raw_df = raw_df[raw_df["format"].str.lower().isin(CONVERT_INPUT_FORMATS)].copy()
    if raw_df.empty:
        st.info("No convertible raw uploads found.")
    else:
        option_items = build_convert_option_items(raw_df, settings.rawdata_dir)
        option_labels = [item["label"] for item in option_items]
        option_map = {item["label"]: int(item["file_id"]) for item in option_items}
        default_file_id = st.session_state.get("convert_selected_file_id")
        default_index = 0
        if default_file_id is not None:
            for idx, item in enumerate(option_items):
                if int(item["file_id"]) == int(default_file_id):
                    default_index = idx
                    break

        ctrl_input, ctrl_output, ctrl_crs, ctrl_run = st.columns([3.6, 1.5, 1.7, 1.2])
        with ctrl_input:
            selected_label = st.selectbox("Input file", options=option_labels, index=default_index)
        input_file_id = option_map[selected_label]
        st.session_state["convert_selected_file_id"] = input_file_id

        with ctrl_output:
            output_format = st.selectbox("Output format", options=["geoparquet", "gpkg"])

        with ctrl_crs:
            crs_mode = st.selectbox("CRS handling", options=["Keep input CRS", "Transform to target CRS"])
        prev_mode = st.session_state.get("convert_prev_crs_mode")
        if prev_mode != crs_mode:
            st.session_state["convert_prev_crs_mode"] = crs_mode
            if crs_mode == "Transform to target CRS":
                st.session_state["open_crs_dialog"] = True

        with ctrl_run:
            st.write("")
            st.write("")
            run_conversion = st.button("Run conversion", type="primary")

        input_row = raw_df.loc[raw_df["file_id"] == input_file_id].iloc[0]
        input_path = Path(str(input_row["abs_path"]))
        input_format = str(input_row["format"]).lower()

        csv_lat_col: str | None = None
        csv_lon_col: str | None = None
        csv_input_crs = "EPSG:4326"

        if input_format in {"csv", "xlsx", "xls"}:
            columns = _tabular_columns(input_path)
            if columns:
                default_lat = columns.index("lat") if "lat" in columns else 0
                default_lon = columns.index("lon") if "lon" in columns else min(1, len(columns) - 1)
                csv_lat_col = st.selectbox("Latitude column", options=columns, index=default_lat)
                csv_lon_col = st.selectbox("Longitude column", options=columns, index=default_lon)
            else:
                csv_lat_col = st.text_input("Latitude column", value="lat")
                csv_lon_col = st.text_input("Longitude column", value="lon")
            csv_input_crs = st.text_input("Input CRS", value="EPSG:4326")

        target_crs = None
        if crs_mode == "Transform to target CRS":
            target_input_col, target_pop_col = st.columns([2.2, 1.0])
            with target_input_col:
                target_crs = st.text_input(
                    "Target CRS",
                    value=st.session_state.get("target_crs", "EPSG:4326"),
                    key="target_crs",
                )
            with target_pop_col:
                st.write("")
                if st.button("CRS 목록", key="open_crs_dialog_btn", width="stretch"):
                    st.session_state["open_crs_dialog"] = True
            if st.session_state.get("open_crs_dialog", False):
                _render_crs_preset_dialog(state_key="target_crs")
                st.session_state["open_crs_dialog"] = False
            preset_help = {code: f"{title} - {desc}" for code, title, desc in CRS_PRESETS}
            if target_crs in preset_help:
                st.caption(f"선택된 CRS: {preset_help[target_crs]}")

        if run_conversion:
            try:
                convert_progress = st.progress(0, text="Starting conversion...")

                def _update_convert_progress(message: str, pct: int) -> None:
                    convert_progress.progress(max(0, min(100, pct)), text=message)

                with get_session() as session:
                    output_file_id = convert_file(
                        session,
                        input_file_id=input_file_id,
                        data_dir=settings.data_dir,
                        output_format=output_format,
                        target_crs=target_crs,
                        csv_lat_col=csv_lat_col,
                        csv_lon_col=csv_lon_col,
                        csv_input_crs=csv_input_crs,
                        progress_callback=_update_convert_progress,
                    )
                convert_progress.empty()

                data_df = _data_table()
                output_rows = data_df.loc[data_df["file_id"] == output_file_id]
                if output_rows.empty:
                    st.success("Conversion complete.")
                else:
                    output_display_id = int(output_rows.iloc[0]["id"])
                    st.success(f"Conversion complete. Data id: {output_display_id}")
            except Exception as exc:
                convert_progress.empty()
                st.error(f"Conversion failed: {exc}")

    data_df = _data_table().copy()
    data_df["name"] = data_df["raw_name"].where(data_df["raw_name"] != "", data_df["name"])
    _render_file_table(
        "변환 데이터 목록",
        data_df,
        table_key="data_table",
        active_tab_on_rerun="Convert",
        include_crs=True,
    )

with tab_browse:
    st.subheader("Data browser and map")

    data_df = _data_table().copy()
    data_df["display_name"] = data_df["abs_path"].map(_data_display_name)
    if data_df.empty:
        st.info("No converted data found.")
    else:
        browse_list_df = data_df.sort_values(by="id", ascending=True).copy()
        file_ids = browse_list_df["file_id"].astype(int).tolist()
        if not file_ids:
            st.info("시각화할 데이터가 없습니다.")
            st.session_state["browse_selected_file_id"] = None
        else:
            selected_file_id = st.session_state.get("browse_selected_file_id")
            if selected_file_id not in file_ids:
                selected_file_id = file_ids[0]
                st.session_state["browse_selected_file_id"] = int(selected_file_id)

            name_map = {
                int(row.file_id): str(row.display_name)
                for row in browse_list_df.itertuples(index=False)
            }
            rows_map = {
                int(row.file_id): int(row.total_rows)
                for row in browse_list_df.itertuples(index=False)
            }

            control_file_col, control_rows_col = st.columns([5, 1.4], gap="medium")
            with control_file_col:
                st.selectbox(
                    "파일 선택",
                    options=file_ids,
                    index=file_ids.index(int(selected_file_id)),
                    format_func=lambda file_id: f"{name_map[int(file_id)]} ({rows_map[int(file_id)]:,} rows)",
                    key="browse_selected_file_id",
                )
            with control_rows_col:
                display_rows = st.number_input(
                    "display rows",
                    min_value=1,
                    value=int(st.session_state.get("browse_display_rows", 1000)),
                    step=100,
                    key="browse_display_rows_input",
                )
                st.session_state["browse_display_rows"] = int(display_rows)

            selected_file_id = st.session_state.get("browse_selected_file_id")
            selected_row_df = data_df.loc[data_df["file_id"] == selected_file_id] if selected_file_id else pd.DataFrame()

            left_col, right_col = st.columns([1, 2], gap="large")

            with left_col:
                if selected_row_df.empty:
                    st.info("선택된 데이터가 없습니다.")
                else:
                    selected_row = selected_row_df.iloc[0]
                    selected_path = Path(str(selected_row["abs_path"]))
                    selected_mtime_ns = selected_path.stat().st_mtime_ns if selected_path.exists() else 0
                    preview_gdf = _cached_geodata(str(selected_path), selected_mtime_ns)
                    preview_data = preview_gdf.drop(columns=preview_gdf.geometry.name, errors="ignore")
                    preview_df = _preview_dataframe(preview_data, max_rows=10)
                    preview_height = 42 + (len(preview_df) * 35)
                    st.dataframe(preview_df, width="stretch", height=preview_height)

            with right_col:
                if selected_row_df.empty:
                    st.info("좌측에서 시각화할 파일을 선택하세요.")
                else:
                    selected_row = selected_row_df.iloc[0]
                    selected_path = Path(str(selected_row["abs_path"]))
                    selected_mtime_ns = selected_path.stat().st_mtime_ns if selected_path.exists() else 0
                    display_rows = int(st.session_state.get("browse_display_rows", 1000))

                    map_cache_key = (int(selected_file_id), display_rows, str(selected_path), selected_mtime_ns)
                    previous_map_key = st.session_state.get("browse_cached_map_key")
                    needs_map_refresh = (
                        map_cache_key != previous_map_key
                        or st.session_state.get("browse_cached_map") is None
                    )

                    if needs_map_refresh:
                        with st.spinner("지도를 준비하는 중..."):
                            gdf = _cached_geodata(str(selected_path), selected_mtime_ns)
                            map_gdf = gdf
                            if len(map_gdf) > display_rows:
                                map_gdf = map_gdf.sample(n=display_rows, random_state=42).copy()
                            st.session_state["browse_cached_map"] = build_map(
                                [(str(selected_row["display_name"]), map_gdf)],
                                max_features=None,
                            )
                        st.session_state["browse_cached_map_key"] = map_cache_key

                    cached_map = st.session_state.get("browse_cached_map")
                    if cached_map is not None:
                        st_folium(
                            cached_map,
                            key="browse_single_map",
                            width=None,
                            height=650,
                            returned_objects=[],
                        )
