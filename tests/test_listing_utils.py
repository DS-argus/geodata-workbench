from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.listing import apply_list_query, build_convert_option_items


def test_apply_list_query_filters_and_paginates() -> None:
    df = pd.DataFrame(
        [
            {"id": 1, "name": "roads", "path": "rawdata/a/roads.shp", "format": "shp"},
            {"id": 2, "name": "buildings", "path": "rawdata/a/buildings.shp", "format": "shp"},
            {"id": 3, "name": "roads", "path": "rawdata/b/roads.shp", "format": "shp"},
            {"id": 4, "name": "poi", "path": "rawdata/poi.csv", "format": "csv"},
        ]
    )

    page_df, total_items, total_pages = apply_list_query(
        df,
        query="roads",
        format_filter=["shp"],
        sort_by="id",
        sort_dir="asc",
        page=1,
        page_size=1,
    )

    assert total_items == 2
    assert total_pages == 2
    assert len(page_df) == 1
    assert int(page_df.iloc[0]["id"]) == 1


def test_apply_list_query_supports_like_pattern() -> None:
    df = pd.DataFrame(
        [
            {"id": 1, "name": "road_main", "path": "rawdata/a/road_main.shp", "format": "shp"},
            {"id": 2, "name": "road_sub", "path": "rawdata/a/road_sub.shp", "format": "shp"},
            {"id": 3, "name": "river", "path": "rawdata/a/river.shp", "format": "shp"},
        ]
    )

    page_df, total_items, total_pages = apply_list_query(
        df,
        query="road_%",
        format_filter=None,
        sort_by="id",
        sort_dir="asc",
        page=1,
        page_size=10,
    )

    assert total_items == 2
    assert total_pages == 1
    assert page_df["name"].tolist() == ["road_main", "road_sub"]


def test_build_convert_option_items_adds_path_scope_tags_for_duplicates(tmp_path: Path) -> None:
    raw_root = tmp_path / "rawdata"
    raw_root.mkdir(parents=True)

    df = pd.DataFrame(
        [
            {
                "file_id": 11,
                "id": 1,
                "name": "행정경계",
                "format": "shp",
                "abs_path": str(raw_root / "city_a" / "bound.shp"),
            },
            {
                "file_id": 12,
                "id": 2,
                "name": "행정경계",
                "format": "shp",
                "abs_path": str(raw_root / "city_b" / "bound.shp"),
            },
        ]
    )

    items = build_convert_option_items(df, raw_root)
    labels = [item["label"] for item in items]

    assert "행정경계 · city_a#1 (shp)" in labels
    assert "행정경계 · city_b#1 (shp)" in labels
