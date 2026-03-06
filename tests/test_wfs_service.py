from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.wfs_service import (
    WfsAutoSplitRetryableError,
    _is_invalid_range_response,
    _collect_features,
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


def test_collect_features_auto_splits_bbox_on_retryable_error(monkeypatch) -> None:
    original_bbox = (0.0, 0.0, 9.0, 9.0)
    filters = [{"type": "BBOX", "geom_column": "ag_geom", "bbox": list(original_bbox)}]
    calls_by_bbox: dict[tuple[float, float, float, float], int] = {}
    progress_events: list[tuple[str, int]] = []

    def fake_build_filter_xml(items):
        bbox = next(item["bbox"] for item in items if item.get("type") == "BBOX")
        return ",".join(str(v) for v in bbox)

    def fake_fetch_wfs_page(*, filter_xml: str | None, **kwargs):
        assert filter_xml is not None
        bbox = tuple(float(v) for v in filter_xml.split(","))
        calls_by_bbox[bbox] = calls_by_bbox.get(bbox, 0) + 1
        if bbox == original_bbox and calls_by_bbox[bbox] == 1:
            raise WfsAutoSplitRetryableError("STARTINDEX 범위 초과(INVALID_RANGE)")
        return {
            "features": [
                {
                    "id": f"feature-{bbox}",
                    "type": "Feature",
                    "properties": {"bbox": str(bbox)},
                    "geometry": {"type": "Point", "coordinates": [bbox[0], bbox[1]]},
                }
            ]
        }

    monkeypatch.setattr("app.services.wfs_service.build_filter_xml", fake_build_filter_xml)
    monkeypatch.setattr("app.services.wfs_service._fetch_wfs_page", fake_fetch_wfs_page)

    features, stats = _collect_features(
        api_key="dummy",
        typename="layer",
        srs_name="EPSG:4326",
        filters=filters,
        bbox_split=1,
        page_size=1000,
        max_features=None,
        cancel_check=None,
        progress_callback=lambda message, percent: progress_events.append((message, percent)),
    )

    assert len(features) == 9
    assert stats["auto_split_events"] >= 1
    assert any("BBOX 자동 분할 적용 (depth 1" in message for message, _ in progress_events)


def test_collect_features_retryable_without_bbox_fails(monkeypatch) -> None:
    def fake_fetch_wfs_page(**kwargs):
        raise WfsAutoSplitRetryableError("WFS 요청 시간 초과")

    monkeypatch.setattr("app.services.wfs_service._fetch_wfs_page", fake_fetch_wfs_page)

    try:
        _collect_features(
            api_key="dummy",
            typename="layer",
            srs_name="EPSG:4326",
            filters=[],
            bbox_split=1,
            page_size=1000,
            max_features=None,
            cancel_check=None,
            progress_callback=None,
        )
    except ValueError as exc:
        assert "BBOX 조건" in str(exc)
    else:
        raise AssertionError("BBOX 없이 retryable 오류가 발생하면 실패해야 합니다.")


def test_collect_features_truncates_tile_when_auto_split_depth_limit_reached(monkeypatch) -> None:
    filters = [{"type": "BBOX", "geom_column": "ag_geom", "bbox": [0.0, 0.0, 9.0, 9.0]}]

    def fake_fetch_wfs_page(**kwargs):
        raise WfsAutoSplitRetryableError("STARTINDEX 범위 초과(INVALID_RANGE)")

    monkeypatch.setattr("app.services.wfs_service._fetch_wfs_page", fake_fetch_wfs_page)

    features, stats = _collect_features(
        api_key="dummy",
        typename="layer",
        srs_name="EPSG:4326",
        filters=filters,
        bbox_split=1,
        page_size=1000,
        max_features=None,
        cancel_check=None,
        progress_callback=None,
    )
    assert features == []
    assert stats["truncated_tiles"] > 0
