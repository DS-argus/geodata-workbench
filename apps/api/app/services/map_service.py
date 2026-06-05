from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely import make_valid


SUPPORTED_MAP_EXTENSIONS = {".parquet", ".gpkg", ".geojson", ".shp"}
MAX_MAP_FEATURES = 1000


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
