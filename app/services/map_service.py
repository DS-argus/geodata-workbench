from __future__ import annotations

from pathlib import Path
import math

import folium
import geopandas as gpd
from folium import FeatureGroup, LayerControl
from shapely import make_valid


SUPPORTED_MAP_EXTENSIONS = {".parquet", ".gpkg", ".geojson", ".shp"}
MAX_MAP_FEATURES = 1000
MAX_TOOLTIP_FIELDS = 12


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


def _normalize_tooltip_value(value):
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


def _prepare_tooltip_gdf(gdf: gpd.GeoDataFrame, tooltip_fields: list[str]) -> gpd.GeoDataFrame:
    if not tooltip_fields:
        return gdf
    tooltip_gdf = gdf.copy()
    for field in tooltip_fields:
        if field not in tooltip_gdf.columns:
            continue
        series = tooltip_gdf[field]
        if str(series.dtype) == "object":
            tooltip_gdf[field] = series.map(_normalize_tooltip_value)
    return tooltip_gdf


def _sanitize_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf

    clean = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if clean.empty:
        return clean

    invalid_mask = ~clean.geometry.is_valid
    if invalid_mask.any():
        fixed_geometry = clean.geometry.copy()
        fixed_geometry.loc[invalid_mask] = fixed_geometry.loc[invalid_mask].apply(make_valid)
        clean = clean.set_geometry(fixed_geometry)
        clean = clean[clean.geometry.notna() & ~clean.geometry.is_empty].copy()

    return clean


def _sample_for_map(
    gdf: gpd.GeoDataFrame,
    max_features: int | None = MAX_MAP_FEATURES,
) -> gpd.GeoDataFrame:
    if max_features is None:
        return gdf
    if len(gdf) <= max_features:
        return gdf
    return gdf.sample(n=max_features, random_state=42).copy()


def load_geodata(path: str | Path) -> gpd.GeoDataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MAP_EXTENSIONS:
        raise ValueError(f"Unsupported map file extension: {suffix}")

    if suffix == ".parquet":
        gdf = gpd.read_parquet(path)
    else:
        gdf = gpd.read_file(path)

    if gdf.crs and str(gdf.crs) != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    return _sanitize_geometries(gdf)


def build_map(
    layers: list[tuple[str, gpd.GeoDataFrame]],
    max_features: int | None = MAX_MAP_FEATURES,
) -> folium.Map:
    base_location = [37.5665, 126.9780]
    zoom_start = 7

    sanitized_layers: list[tuple[str, gpd.GeoDataFrame]] = []
    for name, gdf in layers:
        clean = _sample_for_map(_sanitize_geometries(gdf), max_features=max_features)
        sanitized_layers.append((name, clean))

        if clean.empty:
            continue

        min_x, min_y, max_x, max_y = clean.total_bounds
        if all(math.isfinite(value) for value in (min_x, min_y, max_x, max_y)):
            base_location = [(min_y + max_y) / 2.0, (min_x + max_x) / 2.0]
            break

    fmap = folium.Map(location=base_location, zoom_start=zoom_start, tiles="OpenStreetMap")

    for name, gdf in sanitized_layers:
        if gdf.empty:
            continue
        geom_col = gdf.geometry.name
        tooltip_fields = [str(col) for col in gdf.columns if str(col) != geom_col][:MAX_TOOLTIP_FIELDS]
        tooltip_gdf = _prepare_tooltip_gdf(gdf, tooltip_fields)
        tooltip = None
        if tooltip_fields:
            tooltip = folium.GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=[f"{field}: " for field in tooltip_fields],
                labels=True,
                sticky=True,
            )
        feature_group = FeatureGroup(name=name)
        folium.GeoJson(
            tooltip_gdf.__geo_interface__,
            name=name,
            tooltip=tooltip,
            marker=folium.CircleMarker(radius=4, color="#1f77b4", weight=1, fill=True, fill_opacity=0.85),
            highlight_function=lambda _: {"weight": 3, "fillOpacity": 0.65},
        ).add_to(feature_group)
        feature_group.add_to(fmap)

    LayerControl(collapsed=False).add_to(fmap)
    return fmap
