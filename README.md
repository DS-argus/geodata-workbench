# Geodata Workbench

공간데이터를 업로드해 GeoParquet 또는 GeoPackage(GPKG)로 변환하고, VWorld WFS에서 수집한 데이터를 지도에서 바로 확인하는 로컬 워크벤치입니다.

## 빠른 시작 (권장)

### macOS / Linux

```bash
./setup
```

`./setup`은 Docker Compose 기반 실행을 기본값으로 설정합니다.

```bash
docker compose up -d --build
```

### Windows PowerShell

Windows는 로컬 PostgreSQL/PostGIS, 로컬 Node/npm 실행을 기준으로 합니다.

```ps1
pwsh ./setup.ps1
```

### setup 후 실행 명령 (요약)

```bash
# macOS/Linux: API + Web + DB 컨테이너
docker compose up -d --build
```

```ps1
# Windows: 로컬 API
uv sync
uv run alembic -c apps/api/alembic.ini upgrade head
uv run uvicorn app.api:app --reload --port 8000

# Windows: 로컬 Web
cd apps/web
npm install
npm run dev
```

- 웹 UI: http://localhost:5173
- API 문서: http://localhost:8000/docs

## 프로젝트 구조

- Backend/API: FastAPI (Python), `apps/api/app`
- Frontend/Web: React + Vite, `apps/web`
- DB/Migration: PostgreSQL/PostGIS(현재 메타데이터 저장) + Alembic, `apps/api/alembic`
- WFS catalog: `resources/wfs`
- 수동 수집 도구: `tools/collectors`
- 지도 타일: OpenStreetMap
- WFS 수집: VWorld WFS

## 탭별 기능

### Upload

- Input
  - Shapefile ZIP (`.shp`, `.dbf`, `.shx` 필수, `.prj` 권장)
  - 위도/경도 컬럼이 있는 CSV/Excel
- Output
  - 선택한 형식으로 변환됨: GeoParquet(`.parquet`) 또는 GPKG(`.gpkg`)
- 기능
  - ZIP 업로드 시 `rawdata/`에 원본 저장 후 변환하여 `data/upload/`에 저장
  - 출력 형식 선택 가능: `geoparquet`(기본) 또는 `gpkg`
  - CSV/Excel은 업로드 직후 팝업에서 위도/경도 컬럼 지정
  - CSV/Excel 입력 CRS는 `EPSG:4326`(고정)으로 처리
  - 업로드 목록에서 변환 상태/결과 파일/오류 확인 가능

### WFS Collect

- VWorld API 키를 UI에서 저장 후 재사용
  - `.env`의 `VWORLD_API_KEY`가 있으면 UI에 저장한 키보다 우선 사용
  - UI에서 입력한 VWorld API 키는 DB의 `app_secrets` 테이블에 암호화 저장
- 레이어/출력 형식/SRSNAME 선택 후 즉시 수집
  - EQ/LIKE/BBOX 필터와 AND/OR 조합 지원
  - BBOX 조건 실패 시 3x3 자동 분할 재시도(최대 depth 3)
- 수집 결과를 `data/wfs/`에 바로 저장(GeoParquet 기본, GPKG 선택 가능)
- 백그라운드 Job 실행 + 진행 중 중단 버튼 제공

### Browse & Map

- 기본 파일 선택값은 `없음`
- 선택 시 좌측 Preview(최대 50행), 우측 지도(2/3) 표시
- Point는 Marker Cluster, Polygon은 진한 채움 스타일
- Hover 툴팁, 지도 로딩 오버레이 제공

## 저장 위치

- 원본 업로드: `rawdata/`
- Upload 자동 변환 결과: `data/upload/`
- WFS 수집 결과: `data/wfs/`
