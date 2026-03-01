from __future__ import annotations

from app.services.conversion_service import _build_output_stem


def test_build_output_stem_includes_input_name_and_crs() -> None:
    stem = _build_output_stem(input_name="roads.shp", crs="EPSG:4326")

    assert stem == "roads_EPSG_4326"


def test_build_output_stem_preserves_non_ascii_name() -> None:
    stem = _build_output_stem(input_name="행정경계.shp", crs="EPSG:5179")

    assert stem == "행정경계_EPSG_5179"
