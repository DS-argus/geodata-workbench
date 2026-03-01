# Geodata Workbench

공간데이터를 업로드하고 변환한 뒤, 지도에서 바로 확인하는 로컬 워크벤치입니다.

- Backend: FastAPI (Python)
- Frontend: React + Vite
- DB: PostgreSQL + PostGIS (메타데이터 저장)
- 지도 타일: OpenStreetMap

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

- 파일 업로드 / 폴더 업로드
- 선택 즉시 자동 저장
- 업로드 목록 조회/삭제

### Convert

- 입력 파일, 출력 형식, CRS 처리 선택 후 변환 실행
- `목표 CRS로 변환` 선택 시 목표 CRS 입력/목록 노출
- CSV/Excel 변환 시 팝업에서 위도/경도 컬럼 선택, 입력 CRS 지정
- 컬럼 샘플/숫자 범위와 위경도 참고 범위 확인 가능
- 백그라운드 Job 실행 + 진행 중 중단 버튼 제공

### Browse & Map

- 기본 파일 선택값은 `없음`
- 선택 시 좌측 Preview(최대 50행), 우측 지도(2/3) 표시
- Point는 Marker Cluster, Polygon은 진한 채움 스타일
- Hover 툴팁, 지도 로딩 오버레이 제공

## 저장 위치

- 원본 업로드: `rawdata/`
- 변환 결과: `data/`
