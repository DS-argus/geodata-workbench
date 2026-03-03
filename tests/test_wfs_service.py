from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.wfs_service import (
    _is_invalid_range_response,
    build_filter_xml,
    load_vworld_layer_catalog,
    split_bbox,
)


def test_split_bbox_nine_cells() -> None:
    boxes = split_bbox((0.0, 0.0, 3.0, 3.0), 9)
    assert len(boxes) == 9
    assert boxes[0] == (0.0, 0.0, 1.0, 1.0)
    assert boxes[-1] == (2.0, 2.0, 3.0, 3.0)


def test_build_filter_xml_supports_mixed_conditions() -> None:
    xml = build_filter_xml(
        [
            {"type": "EQ", "column": "sig_cd", "value": "41110"},
            {"type": "LIKE", "column": "emd_nm", "value": "수지*"},
            {"type": "BBOX", "geom_column": "ag_geom", "bbox": [126.5, 36.9, 127.9, 38.5]},
        ]
    )
    assert xml is not None
    assert "PropertyIsEqualTo" in xml
    assert "PropertyIsLike" in xml
    assert "<fes:BBOX>" in xml
    assert "126.5 36.9" in xml


def test_load_vworld_layer_catalog_reads_excel(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.xlsx"
    df = pd.DataFrame(
        {
            "WFS명": ["lt_c_adsigg_info", "lt_c_adsigg_info"],
            "WFS 한글명": ["행정구역도_시군구정보", "행정구역도_시군구정보"],
            "컬럼명(영문)": ["sig_cd", "sig_kor_nm"],
            "컬럼명(한글)": ["시군구코드", "시군구명"],
        }
    )
    df.to_excel(catalog_path, index=False)

    items = load_vworld_layer_catalog(catalog_path)
    sig_item = next(item for item in items if item["typename"] == "lt_c_adsigg_info")
    assert sig_item["typename"] == "lt_c_adsigg_info"
    assert sig_item["display_name"] == "행정구역도_시군구정보"
    assert any(col["name"] == "sig_cd" for col in sig_item["columns"])


def test_build_filter_xml_supports_or_join() -> None:
    xml = build_filter_xml(
        [
            {"type": "EQ", "column": "sig_cd", "value": "41110"},
            {"type": "EQ", "column": "sig_cd", "value": "41130", "join_with_prev": "OR"},
            {"type": "LIKE", "column": "sig_kor_nm", "value": "용인*", "join_with_prev": "AND"},
        ]
    )
    assert xml is not None
    assert "<fes:Or>" in xml
    assert "<fes:And>" in xml


def test_invalid_range_response_detector() -> None:
    xml = '<ServiceException code="INVALID_RANGE">STARTINDEX 파라미터의 값이 유효한 범위를 넘었습니다.</ServiceException>'
    assert _is_invalid_range_response(xml) is True
