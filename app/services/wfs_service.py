from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
import requests

from app.services.storage_service import allocate_output_path


VWORLD_BASE_URL = "https://api.vworld.kr/req/wfs"
VWORLD_PAGE_SIZE = 1000


class WfsCollectionCancelledError(RuntimeError):
    pass


class WfsPaginationEndError(RuntimeError):
    pass


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    slug = re.sub(r"\s+", "_", cleaned).strip("_")
    return slug or "dataset"


def _build_condition_like(column: str, value: str) -> str:
    return (
        f'<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">'
        f"<fes:ValueReference>{column}</fes:ValueReference>"
        f"<fes:Literal>{value}</fes:Literal>"
        f"</fes:PropertyIsLike>"
    )


def _build_condition_eq(column: str, value: str) -> str:
    return (
        f"<fes:PropertyIsEqualTo>"
        f"<fes:ValueReference>{column}</fes:ValueReference>"
        f"<fes:Literal>{value}</fes:Literal>"
        f"</fes:PropertyIsEqualTo>"
    )


def _build_condition_bbox(
    bbox: tuple[float, float, float, float],
    geom_column: str = "ag_geom",
) -> str:
    xmin, ymin, xmax, ymax = bbox
    return (
        f"<fes:BBOX>"
        f"<fes:ValueReference>{geom_column}</fes:ValueReference>"
        f'<gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
        f"<gml:lowerCorner>{xmin} {ymin}</gml:lowerCorner>"
        f"<gml:upperCorner>{xmax} {ymax}</gml:upperCorner>"
        f"</gml:Envelope>"
        f"</fes:BBOX>"
    )


def _extract_wfs_error_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    patterns = [
        r"<ows:ExceptionText>(.*?)</ows:ExceptionText>",
        r"<ExceptionText>(.*?)</ExceptionText>",
        r"<ServiceException[^>]*>(.*?)</ServiceException>",
        r"<title>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]
    for pattern in patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if matched:
            value = re.sub(r"\s+", " ", matched.group(1)).strip()
            if value:
                return value
    compact = re.sub(r"\s+", " ", text)
    if compact.startswith("<"):
        return compact[:240]
    return compact[:180]


def _is_invalid_range_response(raw_text: str) -> bool:
    if not raw_text:
        return False
    lowered = raw_text.lower()
    return ("invalid_range" in lowered) or ("startindex 파라미터의 값이 유효한 범위를 넘었습니다" in lowered)


def split_bbox(
    bbox: tuple[float, float, float, float], splits: int
) -> list[tuple[float, float, float, float]]:
    if splits <= 1:
        return [bbox]

    minx, miny, maxx, maxy = bbox
    if splits == 4:
        xs = [minx, (minx + maxx) / 2, maxx]
        ys = [miny, (miny + maxy) / 2, maxy]
    elif splits >= 9:
        dx = (maxx - minx) / 3
        dy = (maxy - miny) / 3
        xs = [minx, minx + dx, minx + 2 * dx, maxx]
        ys = [miny, miny + dy, miny + 2 * dy, maxy]
    else:
        return [bbox]

    boxes: list[tuple[float, float, float, float]] = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            boxes.append((xs[i], ys[j], xs[i + 1], ys[j + 1]))
    return boxes


def _bbox_from_filters(filters: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    for item in filters:
        if str(item.get("type", "")).upper() != "BBOX":
            continue
        bbox_raw = item.get("bbox") or item.get("value")
        if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
            return tuple(float(v) for v in bbox_raw)
    return None


def _replace_or_append_bbox_filter(
    filters: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    next_filters: list[dict[str, Any]] = []
    replaced = False
    for item in filters:
        if str(item.get("type", "")).upper() == "BBOX":
            next_filters.append(
                {
                    "type": "BBOX",
                    "geom_column": item.get("geom_column") or item.get("column") or "ag_geom",
                    "bbox": list(bbox),
                    "join_with_prev": item.get("join_with_prev"),
                }
            )
            replaced = True
        else:
            next_filters.append(dict(item))
    if not replaced:
        next_filters.append({"type": "BBOX", "geom_column": "ag_geom", "bbox": list(bbox), "join_with_prev": "AND"})
    return next_filters


def _fetch_layer_wgs84_bbox(
    *,
    api_key: str,
    typename: str,
) -> tuple[float, float, float, float] | None:
    params = {
        "KEY": api_key,
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetCapabilities",
    }
    response = requests.get(VWORLD_BASE_URL, params=params, timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    for feature in root.iter():
        if not str(feature.tag).lower().endswith("featuretype"):
            continue
        feature_name = None
        lower_corner = None
        upper_corner = None
        for child in feature:
            tag = str(child.tag).lower()
            if tag.endswith("name"):
                feature_name = (child.text or "").strip()
            elif tag.endswith("wgs84boundingbox"):
                for box_child in child:
                    box_tag = str(box_child.tag).lower()
                    if box_tag.endswith("lowercorner"):
                        lower_corner = (box_child.text or "").strip()
                    elif box_tag.endswith("uppercorner"):
                        upper_corner = (box_child.text or "").strip()
        if feature_name != typename or not lower_corner or not upper_corner:
            continue
        minx, miny = [float(v) for v in lower_corner.split()]
        maxx, maxy = [float(v) for v in upper_corner.split()]
        return (minx, miny, maxx, maxy)
    return None


def build_filter_xml(filters: list[dict[str, Any]]) -> str | None:
    if not filters:
        return None

    conditions: list[tuple[str | None, str]] = []
    for index, item in enumerate(filters):
        ftype = str(item.get("type", "")).upper()
        join_with_prev = str(item.get("join_with_prev") or "AND").upper()
        if join_with_prev not in {"AND", "OR"}:
            join_with_prev = "AND"
        join = join_with_prev if index > 0 else None
        if ftype == "EQ":
            column = str(item.get("column", "")).strip()
            value = str(item.get("value", "")).strip()
            if column:
                conditions.append((join, _build_condition_eq(column, value)))
        elif ftype == "LIKE":
            column = str(item.get("column", "")).strip()
            value = str(item.get("value", "")).strip()
            if column and value:
                conditions.append((join, _build_condition_like(column, value)))
        elif ftype == "BBOX":
            geom_column = str(item.get("geom_column") or item.get("column") or "ag_geom")
            bbox_raw = item.get("bbox") or item.get("value")
            if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
                bbox = tuple(float(v) for v in bbox_raw)
                conditions.append((join, _build_condition_bbox(bbox, geom_column=geom_column)))

    if not conditions:
        return None

    ns = (
        'xmlns:fes="http://www.opengis.net/fes/2.0" '
        'xmlns:gml="http://www.opengis.net/gml/3.2"'
    )
    expression = conditions[0][1]
    for join, condition in conditions[1:]:
        operator = "Or" if join == "OR" else "And"
        expression = f"<fes:{operator}>{expression}{condition}</fes:{operator}>"
    return f"<fes:Filter {ns}>{expression}</fes:Filter>"


def _fetch_wfs_page(
    *,
    api_key: str,
    typename: str,
    srs_name: str,
    start_index: int,
    count: int,
    filter_xml: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "KEY": api_key,
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAME": typename,
        "SRSNAME": srs_name,
        "OUTPUT": "application/json",
        "COUNT": count,
        "STARTINDEX": start_index,
    }
    if filter_xml:
        params["FILTER"] = filter_xml

    response = requests.get(VWORLD_BASE_URL, params=params, timeout=180)
    if response.status_code >= 400:
        detail = _extract_wfs_error_text(response.text)
        if detail:
            raise ValueError(f"WFS 요청 실패 (HTTP {response.status_code}): {detail}")
        response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        if _is_invalid_range_response(response.text):
            raise WfsPaginationEndError("STARTINDEX 범위를 초과해 페이지 수집을 종료합니다.") from exc
        for encoding in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                decoded = response.content.decode(encoding)
                return json.loads(decoded)
            except Exception:
                continue
        detail = _extract_wfs_error_text(response.text)
        if detail:
            raise ValueError(f"WFS 응답이 JSON이 아니며 오류를 반환했습니다: {detail}") from exc
        raise ValueError("WFS 응답을 JSON으로 해석하지 못했습니다. 선택한 레이어의 응답 형식을 확인해 주세요.") from exc


def _collect_features(
    *,
    api_key: str,
    typename: str,
    srs_name: str,
    filters: list[dict[str, Any]],
    bbox_split: int,
    fallback_bbox: tuple[float, float, float, float] | None,
    page_size: int,
    max_features: int | None,
    cancel_check: Callable[[], bool] | None,
    progress_callback: Callable[[str, int], None] | None,
) -> list[dict[str, Any]]:
    if cancel_check and cancel_check():
        raise WfsCollectionCancelledError("WFS 수집이 취소되었습니다.")

    features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    pending_segments: list[tuple[list[dict[str, Any]], int]] = []

    input_bbox = _bbox_from_filters(filters)
    if input_bbox is not None and bbox_split > 1:
        for box in split_bbox(input_bbox, bbox_split):
            pending_segments.append((_replace_or_append_bbox_filter(filters, box), 1))
    elif input_bbox is None and fallback_bbox is not None:
        # VWorld WFS limits STARTINDEX to <= 1000; split the global extent up-front
        # so layers with >2000 features can still be collected completely.
        initial_split = max(4, bbox_split if bbox_split > 1 else 4)
        for box in split_bbox(fallback_bbox, initial_split):
            pending_segments.append((_replace_or_append_bbox_filter(filters, box), 1))
    else:
        pending_segments.append((filters, 0))
    completed_segments = 0
    while pending_segments:
        segment_filters, split_depth = pending_segments.pop(0)
        start_index = 0
        while True:
            if cancel_check and cancel_check():
                raise WfsCollectionCancelledError("WFS 수집이 취소되었습니다.")

            try:
                payload = _fetch_wfs_page(
                    api_key=api_key,
                    typename=typename,
                    srs_name=srs_name,
                    start_index=start_index,
                    count=page_size,
                    filter_xml=build_filter_xml(segment_filters),
                )
            except WfsPaginationEndError:
                segment_bbox = _bbox_from_filters(segment_filters) or fallback_bbox
                if segment_bbox is not None and split_depth < 3:
                    split_count = max(4, bbox_split if bbox_split > 1 else 4)
                    child_boxes = split_bbox(segment_bbox, split_count)
                    for child_box in child_boxes:
                        pending_segments.append(
                            (_replace_or_append_bbox_filter(segment_filters, child_box), split_depth + 1)
                        )
                break
            page_features = payload.get("features", [])
            if not page_features:
                break

            for feature in page_features:
                fid = feature.get("id")
                key = str(fid) if fid is not None else f"idx_{len(features)}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                features.append(feature)
                if max_features is not None and len(features) >= max_features:
                    return features

            if len(page_features) < page_size:
                break
            start_index += page_size
        completed_segments += 1
        if progress_callback:
            total_hint = completed_segments + len(pending_segments) + 1
            percent = 20 + int((completed_segments / total_hint) * 40)
            progress_callback("WFS 데이터를 수집하는 중입니다.", min(percent, 60))

    return features


def _load_catalog_dataframe(catalog_path: Path) -> pd.DataFrame:
    if not catalog_path.exists():
        raise FileNotFoundError(f"WFS 컬럼정보 파일을 찾을 수 없습니다: {catalog_path}")
    df = pd.read_excel(catalog_path)
    required = {"WFS명", "WFS 한글명", "컬럼명(영문)", "컬럼명(한글)"}
    if not required.issubset(set(df.columns)):
        raise ValueError("WFS 컬럼정보 파일의 컬럼 구성이 올바르지 않습니다.")
    return df


def _catalog_layers_by_typename(catalog_path: Path) -> dict[str, dict[str, Any]]:
    df = _load_catalog_dataframe(catalog_path)
    grouped = df.groupby(df["WFS명"].astype(str), sort=True)
    output: dict[str, dict[str, Any]] = {}
    for typename, rows in grouped:
        dedup = rows.drop_duplicates(subset=["컬럼명(영문)"])
        display_name = str(rows.iloc[0]["WFS 한글명"]).strip()
        columns = [
            {
                "name": str(row["컬럼명(영문)"]).strip(),
                "name_ko": str(row["컬럼명(한글)"]).strip(),
            }
            for _, row in dedup.iterrows()
        ]
        output[str(typename).strip()] = {
            "display_name": display_name,
            "columns": columns,
        }
    return output


def load_vworld_layer_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    layer_map = _catalog_layers_by_typename(catalog_path)
    items: list[dict[str, Any]] = []
    ordered = sorted(layer_map.items(), key=lambda item: str(item[1].get("display_name", "")))
    for typename, info in ordered:
        items.append(
            {
                "key": typename,
                "display_name": info["display_name"],
                "typename": typename,
                "catalog_name": info["display_name"],
                "default_bbox_split": 1,
                "default_filters": [],
                "columns": info["columns"],
            }
        )
    return items


def collect_vworld_layer(
    *,
    api_key: str,
    layer_typename: str,
    output_format: str,
    data_dir: Path,
    srs_name: str,
    catalog_path: Path,
    filters: list[dict[str, Any]] | None = None,
    bbox_split: int = 1,
    max_features: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> tuple[Path, gpd.GeoDataFrame]:
    layer_map = _catalog_layers_by_typename(catalog_path)
    layer_info = layer_map.get(layer_typename)
    if layer_info is None:
        raise ValueError("지원하지 않는 WFS 레이어입니다.")

    if output_format not in {"geoparquet", "gpkg"}:
        raise ValueError("출력 형식은 geoparquet 또는 gpkg 여야 합니다.")

    typename = layer_typename
    effective_filters = list(filters) if filters is not None else []
    effective_split = int(bbox_split if bbox_split > 0 else 1)

    if progress_callback:
        progress_callback("WFS 요청을 준비하는 중입니다.", 10)
    layer_bbox = _fetch_layer_wgs84_bbox(api_key=api_key, typename=typename)

    features = _collect_features(
        api_key=api_key,
        typename=typename,
        srs_name=srs_name,
        filters=effective_filters,
        bbox_split=effective_split,
        fallback_bbox=layer_bbox,
        page_size=VWORLD_PAGE_SIZE,
        max_features=max_features,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )
    if not features:
        raise ValueError("조건에 맞는 WFS 피처를 찾지 못했습니다.")

    if progress_callback:
        progress_callback("수집 데이터를 공간데이터로 변환하는 중입니다.", 70)
    gdf = gpd.GeoDataFrame.from_features(features, crs=srs_name)
    if gdf.empty:
        raise ValueError("수집된 피처가 비어 있습니다.")

    if cancel_check and cancel_check():
        raise WfsCollectionCancelledError("WFS 수집이 취소되었습니다.")

    crs_text = gdf.crs.to_string() if gdf.crs else srs_name
    layer_label = str(layer_info.get("display_name") or typename)
    stem = f"{_safe_slug(layer_label)}_{_safe_slug(crs_text)}"
    ext = "parquet" if output_format == "geoparquet" else "gpkg"
    output_path = allocate_output_path(data_dir, stem, ext)

    if progress_callback:
        progress_callback("파일로 저장하는 중입니다.", 85)
    if output_format == "geoparquet":
        gdf.to_parquet(output_path, index=False)
    else:
        gdf.to_file(output_path, driver="GPKG")

    if progress_callback:
        progress_callback("WFS 수집이 완료되었습니다.", 100)
    return output_path, gdf
    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
            for element in root.iter():
                tag = str(element.tag).lower()
                if tag.endswith("exceptiontext") or tag.endswith("serviceexception"):
                    if element.text and element.text.strip():
                        return re.sub(r"\s+", " ", element.text.strip())
        except Exception:
            pass
