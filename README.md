# Geodata Workbench

공간데이터를 업로드하면 즉시 변환하고, 지도에서 바로 확인하는 로컬 워크벤치입니다.

- Backend: FastAPI (Python)
- Frontend: React + Vite
- DB: PostgreSQL + PostGIS (메타데이터 저장)
- 지도 타일: OpenStreetMap
- WFS 수집: VWorld WFS

## 실행 (권장: Docker만 사용)

```bash
docker compose up -d --build
```

- 웹 UI: http://localhost:5173
- API 문서: http://localhost:8000/docs

## 입력 형식

1. 공간데이터 구성 파일이 포함된 폴더 또는 ZIP

- Shapefile 기준 `.shp`, `.dbf`, `.shx` (권장 `.prj`) 포함 필요

2. 위도/경도 컬럼이 포함된 CSV 또는 Excel (`.xlsx`, `.xls`)

- CSV/Excel은 파일 업로드에서 직접 선택

## 탭별 기능

### Upload

- 파일/폴더 업로드 시 원본 저장 후 자동 변환 실행
- 출력 형식 선택 가능: `geoparquet`(기본) 또는 `gpkg`
- CSV/Excel은 업로드 직후 팝업에서 위도/경도 컬럼 지정
- CSV/Excel 입력 CRS는 `EPSG:4326`(고정)으로 처리
- 업로드 목록에서 변환 상태/결과 파일/오류 확인 가능

### WFS Collect

- VWorld API 키를 UI에서 저장 후 재사용
- 레이어/출력 형식/SRSNAME 선택 후 즉시 수집
- EQ/LIKE/BBOX 필터 + BBOX 분할(1/4/9) 설정
- 수집 결과를 `data/`에 바로 저장(GeoParquet 기본, GPKG 선택 가능)
- 백그라운드 Job 실행 + 진행 중 중단 버튼 제공

### Browse & Map

- 기본 파일 선택값은 `없음`
- 선택 시 좌측 Preview(최대 50행), 우측 지도(2/3) 표시
- Point는 Marker Cluster, Polygon은 진한 채움 스타일
- Hover 툴팁, 지도 로딩 오버레이 제공

## 저장 위치

- 원본 업로드: `rawdata/`
- Upload 자동 변환 및 WFS 수집 결과: `data/`
