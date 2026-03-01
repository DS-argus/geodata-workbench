from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

from app.services.map_service import MAX_MAP_FEATURES, _sample_for_map, build_map, load_geodata


def test_load_geodata_from_parquet(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(126.9780, 37.5665)], crs="EPSG:4326")
    path = tmp_path / "sample.parquet"
    gdf.to_parquet(path, index=False)

    loaded = load_geodata(path)

    assert len(loaded) == 1
    assert loaded.crs.to_epsg() == 4326


def test_build_map_returns_folium_map() -> None:
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(126.9780, 37.5665)], crs="EPSG:4326")

    fmap = build_map([("layer-a", gdf)])

    assert fmap is not None


def test_build_map_handles_invalid_geometry() -> None:
    # Self-intersection polygon ("bowtie"), which is invalid.
    invalid_polygon = Polygon(
        [
            (126.5619, 37.2494),
            (126.5623, 37.2498),
            (126.5623, 37.2494),
            (126.5619, 37.2498),
            (126.5619, 37.2494),
        ]
    )
    gdf = gpd.GeoDataFrame({"name": ["invalid"]}, geometry=[invalid_polygon], crs="EPSG:4326")

    fmap = build_map([("invalid-layer", gdf)])

    assert fmap is not None


def test_sample_for_map_limits_large_layers() -> None:
    gdf = gpd.GeoDataFrame(
        {"idx": list(range(MAX_MAP_FEATURES + 200))},
        geometry=[Point(126.97 + i * 0.00001, 37.56 + i * 0.00001) for i in range(MAX_MAP_FEATURES + 200)],
        crs="EPSG:4326",
    )

    sampled = _sample_for_map(gdf)

    assert len(sampled) == MAX_MAP_FEATURES
