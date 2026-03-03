"""
VWorld WFS API를 사용하여 행정구역 데이터를 Parquet으로 저장

사용법:
    python WFS.py                    # 전체 레이어 다운로드
    python WFS.py --layer 시군구     # 특정 레이어만 다운로드
    python WFS.py --layer 시군구 읍면동  # 여러 레이어 다운로드
    python WFS.py --list             # 레이어 목록 출력
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# import pandas as pd
import geopandas as gpd
import requests
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 설정
# ============================================================

BASE_URL = "https://api.vworld.kr/req/wfs"
API_KEY = os.getenv("VWORLD_API_KEY")
SRSNAME = "EPSG:5186"
PAGE_SIZE = 1000

# 경기도 BBOX (EPSG:4326 경위도)
BBOX_GYEONGGI = (126.5, 36.89, 127.90, 38.5)  # (minx, miny, maxx, maxy)


def split_bbox(
    bbox: Tuple[float, float, float, float], splits: int
) -> List[Tuple[float, float, float, float]]:
    """BBOX를 n등분 (4, 9 지원)

    Args:
        bbox: (minx, miny, maxx, maxy)
        splits: 분할 수 (1=없음, 4=2x2, 9=3x3)

    Returns:
        분할된 BBOX 리스트
    """
    if splits <= 1:
        return [bbox]

    minx, miny, maxx, maxy = bbox

    if splits == 4:
        # 2x2 = 4등분
        xs = [minx, (minx + maxx) / 2, maxx]
        ys = [miny, (miny + maxy) / 2, maxy]
    elif splits >= 9:
        # 3x3 = 9등분
        dx = (maxx - minx) / 3
        dy = (maxy - miny) / 3
        xs = [minx, minx + dx, minx + 2 * dx, maxx]
        ys = [miny, miny + dy, miny + 2 * dy, maxy]
    else:
        return [bbox]

    # 그리드 생성
    boxes = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            boxes.append((xs[i], ys[j], xs[i + 1], ys[j + 1]))

    return boxes


# 레이어 정의
# filters: [(column, type, value), ...] - 여러 조건 가능
LAYERS: Dict[str, Dict[str, Any]] = {
    "시군구": {
        "typename": "lt_c_adsigg_info",
        "filters": [("sig_cd", "LIKE", "41*")],
    },
    "읍면동": {
        "typename": "lt_c_ademd_info",
        "filters": [("emd_cd", "LIKE", "41*")],
    },
    "리": {
        "typename": "lt_c_adri_info",
        "filters": [("li_cd", "LIKE", "41*")],
    },
    "초등학교학교군": {
        "typename": "lt_c_desch",
        "filters": [("edu_up_cd", "EQ", "7530000")],
    },
    "중학교학교군": {
        "typename": "lt_c_dmsch",
        "filters": [("edu_up_cd", "EQ", "7530000")],
    },
    "고등학교학교군": {
        "typename": "lt_c_dhsch",
        "filters": [("edu_up_cd", "EQ", "7530000")],
    },
    "교육행정구역": {
        "typename": "lt_c_eadist",
        "filters": [("edu_up_cd", "EQ", "7530000")],
    },
    "교통노드": {
        "typename": "lt_p_moctnode",
        "filters": [
            ("node_type", "EQ", "106"),
            ("ag_geom", "BBOX", BBOX_GYEONGGI),
        ],
        "bbox_split": 9,  # BBOX 9등분 (API 제한 우회)
    },
    "하천망": {
        "typename": "lt_c_wkmstrm",
        "filters": [
            ("ag_geom", "BBOX", BBOX_GYEONGGI),
        ],
    },
}


# ============================================================
# 필터 생성
# ============================================================


def build_condition_like(column: str, value: str) -> str:
    """LIKE 조건 (패턴 매칭)
    
    Args:
        column: 컬럼명
        value: 패턴 값 (와일드카드 포함 가능, 예: "41*", "*서울*", "41??")
    """
    return (
        f'<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">'
        f"<fes:ValueReference>{column}</fes:ValueReference>"
        f"<fes:Literal>{value}</fes:Literal>"
        f"</fes:PropertyIsLike>"
    )


def build_condition_eq(column: str, value: str) -> str:
    """EQ 조건 (정확히 일치)"""
    return (
        f"<fes:PropertyIsEqualTo>"
        f"<fes:ValueReference>{column}</fes:ValueReference>"
        f"<fes:Literal>{value}</fes:Literal>"
        f"</fes:PropertyIsEqualTo>"
    )


def build_condition_bbox(
    bbox: Tuple[float, float, float, float],
    geom_column: str = "ag_geom",
) -> str:
    """BBOX 조건

    Args:
        bbox: (xmin, ymin, xmax, ymax) = (lon_min, lat_min, lon_max, lat_max)
        geom_column: geometry 컬럼명

    Note:
        VWorld WFS: lowerCorner/upperCorner는 (lon lat) 순서로 사용
    """
    xmin, ymin, xmax, ymax = bbox  # lon_min, lat_min, lon_max, lat_max
    return (
        f"<fes:BBOX>"
        f"<fes:ValueReference>{geom_column}</fes:ValueReference>"
        f'<gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
        f"<gml:lowerCorner>{xmin} {ymin}</gml:lowerCorner>"
        f"<gml:upperCorner>{xmax} {ymax}</gml:upperCorner>"
        f"</gml:Envelope>"
        f"</fes:BBOX>"
    )


def build_filter(filters: List[Tuple]) -> Optional[str]:
    """필터 XML 생성 (다중 조건 지원)

    filters 형식:
        - ("column", "EQ", "value")
        - ("column", "LIKE", "value")
        - ("geom_column", "BBOX", (minx, miny, maxx, maxy))
    """
    if not filters:
        return None

    conditions = []

    for item in filters:
        filter_type = item[1]

        if filter_type == "EQ":
            column, _, value = item
            conditions.append(build_condition_eq(column, value))
        elif filter_type == "LIKE":
            column, _, value = item
            conditions.append(build_condition_like(column, value))
        elif filter_type == "BBOX":
            geom_column, _, bbox = item
            conditions.append(build_condition_bbox(bbox, geom_column))

    if not conditions:
        return None

    # 네임스페이스
    ns = (
        'xmlns:fes="http://www.opengis.net/fes/2.0" '
        'xmlns:gml="http://www.opengis.net/gml/3.2"'
    )

    # 단일 조건이면 And 없이, 다중 조건이면 And로 감싸기
    if len(conditions) == 1:
        return f"<fes:Filter {ns}>{conditions[0]}</fes:Filter>"
    else:
        inner = "".join(conditions)
        return f"<fes:Filter {ns}><fes:And>{inner}</fes:And></fes:Filter>"


# ============================================================
# API 호출
# ============================================================


def fetch_wfs(
    layer_name: str,
    start_index: int = 0,
    filter_xml: Optional[str] = None,
) -> Optional[Dict]:
    """WFS API 호출"""
    params = {
        "KEY": API_KEY,
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAME": layer_name,
        "SRSNAME": SRSNAME,
        "OUTPUT": "application/json",
        "COUNT": PAGE_SIZE,
        "STARTINDEX": start_index,
    }
    if filter_xml:
        params["FILTER"] = filter_xml

    try:
        response = requests.get(BASE_URL, params=params, timeout=300)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code in (400, 500):
            return None
        print(f"✗ HTTP 에러: {e}")
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"✗ 요청 실패: {e}")
        return None


def fetch_all_features(
    layer_name: str,
    filter_xml: Optional[str] = None,
) -> List[Dict]:
    """모든 피처 수집 (페이지네이션)"""
    all_features = []
    seen_ids = set()
    start_index = 0
    page = 1

    while True:
        print(f"    - 페이지 {page} (startindex={start_index})...", end=" ")
        data = fetch_wfs(layer_name, start_index=start_index, filter_xml=filter_xml)

        if not data or "features" not in data:
            if all_features:
                print("(API 제한, 수집 종료)")
            else:
                print("✗ 실패")
            break

        features = data["features"]
        count = len(features)
        print(f"✓ {count}개")

        if count == 0:
            break

        # feature의 id를 중복 체크용 key로 사용
        for f in features:
            fid = f.get("id")
            if fid is None:
                fid = f"_idx_{len(all_features)}"
            if fid not in seen_ids:
                seen_ids.add(fid)
                all_features.append(f)

        if count < PAGE_SIZE:
            break

        start_index += PAGE_SIZE
        page += 1

    return all_features


def features_to_dataframe(features: List[Dict]) -> gpd.GeoDataFrame:
    """GeoJSON features -> GeoDataFrame (공간 데이터)"""
    if not features:
        return gpd.GeoDataFrame()

    # geopandas의 from_features를 사용하여 GeoJSON features를 직접 변환
    # 이렇게 하면 geometry가 shapely geometry 객체로 자동 변환됨
    gdf = gpd.GeoDataFrame.from_features(features, crs=SRSNAME)
    return gdf


# ============================================================
# 메인
# ============================================================


def download_layer(
    display_name: str,
    config: Dict[str, Any],
    output_dir: Path,
) -> bool:
    """레이어 다운로드 및 저장"""
    typename = config["typename"]
    filters = config.get("filters", [])
    bbox_split = config.get("bbox_split", 1)

    print(f"\n[{display_name}] 데이터 수집 중...")
    print(f"  - typename: {typename}")

    # BBOX 필터 찾기 및 분할 처리
    bbox_filter = None
    bbox_geom_col = None
    non_bbox_filters = []

    for item in filters:
        if item[1] == "BBOX":
            bbox_geom_col = item[0]
            bbox_filter = item[2]  # (minx, miny, maxx, maxy)
        else:
            non_bbox_filters.append(item)

    # 필터 정보 출력
    if filters:
        filter_parts = []
        for item in filters:
            ftype = item[1]
            if ftype == "BBOX":
                geom_col, _, bbox = item
                filter_parts.append(f"BBOX({geom_col}, {bbox})")
            else:
                col, _, val = item
                filter_parts.append(f"{col} {ftype} '{val}'")
        print(f"  - 필터: {' AND '.join(filter_parts)}")
        if bbox_split > 1:
            print(f"  - BBOX 분할: {bbox_split}등분")
    else:
        print(f"  - 필터: 없음 (전체 조회)")

    # BBOX 분할 처리
    all_features = []
    seen_ids = set()

    if bbox_filter and bbox_split > 1:
        # BBOX를 분할해서 각각 조회
        split_boxes = split_bbox(bbox_filter, bbox_split)
        for i, sub_bbox in enumerate(split_boxes, 1):
            print(f"  [영역 {i}/{len(split_boxes)}] {sub_bbox}")
            # 분할된 BBOX로 필터 재구성
            current_filters = non_bbox_filters + [(bbox_geom_col, "BBOX", sub_bbox)]
            filter_xml = build_filter(current_filters)
            features = fetch_all_features(typename, filter_xml)

            # 중복 제거하며 추가
            for f in features:
                fid = f.get("id")
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    all_features.append(f)
    else:
        # 분할 없이 일반 조회
        filter_xml = build_filter(filters) if filters else None
        all_features = fetch_all_features(typename, filter_xml)

    if not all_features:
        print("    ✗ 데이터 없음")
        return False

    gdf = features_to_dataframe(all_features)
    print(f"  ✓ 총 {len(gdf)}개 피처 수집")

    output_file = output_dir / f"{display_name}.parquet"
    # geopandas의 to_parquet은 GeoParquet 형식으로 저장 (공간 데이터 최적화)
    gdf.to_parquet(output_file, index=False)
    print(f"  ✓ 저장: {output_file} (GeoParquet 형식)")

    return True


def main():
    parser = argparse.ArgumentParser(description="VWorld WFS API로 데이터 다운로드")
    parser.add_argument("--layer", nargs="*", help="레이어명")
    parser.add_argument("--list", action="store_true", help="레이어 목록")
    args = parser.parse_args()

    if args.list:
        print("레이어 목록:")
        for name, config in LAYERS.items():
            print(f"  {name}:")
            print(f"    - typename: {config['typename']}")
            filters = config.get("filters", [])
            for item in filters:
                ftype = item[1]
                if ftype == "BBOX":
                    geom_col, _, bbox = item
                    print(f"    - 필터: BBOX({geom_col}, {bbox})")
                else:
                    col, _, val = item
                    print(f"    - 필터: {col} {ftype} '{val}'")
        return

    # 레이어 선택
    target_layers = (
        {n: LAYERS[n] for n in args.layer if n in LAYERS} if args.layer else LAYERS
    )

    if not target_layers:
        print("다운로드할 레이어가 없습니다.")
        return

    print("=" * 50)
    print("VWorld WFS - 데이터 다운로드")
    print("=" * 50)
    print(f"레이어: {', '.join(target_layers.keys())}")

    output_dir = Path(__file__).parent / "output" / "WFS"
    output_dir.mkdir(parents=True, exist_ok=True)

    success = fail = 0
    for name, config in target_layers.items():
        if download_layer(name, config, output_dir):
            success += 1
        else:
            fail += 1

    print(f"\n완료! 성공: {success}, 실패: {fail}")


if __name__ == "__main__":
    main()
