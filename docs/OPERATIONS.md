# Geodata Workbench 운영/개발 가이드

이 문서는 운영자/개발자를 위한 기술 문서입니다.  
일반 사용자 안내는 `README.md`를 참고하세요.

## 1) 아키텍처 개요

- `web` (`apps/web`): React + Vite UI (포트 5173)
- `api` (`apps/api/app`): FastAPI 백엔드 (포트 8000)
- `db`: PostgreSQL + PostGIS (포트 5432)
- 원본 파일 저장: `rawdata/`
- 변환 결과 저장: `data/`
- DB에는 메타데이터(`files`, `jobs`, `datasets`, `app_secrets`)만 저장, 공간 본문은 파일로 저장

## 2) Setup 기반 초기화 (권장)

초기 설치/모드 설정은 OS별 진입점을 사용합니다.

```bash
# macOS/Linux
./setup
```

```ps1
# Windows PowerShell
pwsh ./setup.ps1
```

## 3) 실행 모드 가이드

- macOS/Linux: Docker Compose로 API, Web, PostgreSQL/PostGIS 실행
- Windows: 로컬 PostgreSQL/PostGIS와 로컬 Node/npm 실행

## 4) setup 후 실행 명령 (요약)

### macOS/Linux

```bash
docker compose up -d --build
```

### Windows

```ps1
# API
uv sync
uv run alembic -c apps/api/alembic.ini upgrade head
uv run uvicorn app.api:app --reload --port 8000

# Web
cd apps/web
npm install
npm run dev
```

## 5) Docker 운영

### 상태 확인

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f web
```

### 재시작

```bash
docker compose restart api web
```

## 6) DB 마이그레이션(Alembic)

현재 정책:

- Docker에서 `api` 컨테이너 시작 시 `alembic -c apps/api/alembic.ini upgrade head` 자동 실행
- 로컬 개발(직접 `uvicorn` 실행) 시에는 수동 실행 필요

```bash
uv run alembic -c apps/api/alembic.ini upgrade head
```

마이그레이션 생성(스키마 변경 시):

```bash
uv run alembic -c apps/api/alembic.ini revision -m "설명"
```

## 7) Windows 로컬 개발

```ps1
uv sync
uv run alembic -c apps/api/alembic.ini upgrade head
uv run uvicorn app.api:app --reload --port 8000

cd apps/web
npm install
npm run dev
```

## 8) 주요 경로

- 백엔드 API 엔트리: `apps/api/app/api.py`
- 수집 로직: `apps/api/app/collectors/`
- 신규 수집원(예: geocoder)은 `apps/api/app/collectors/` 아래에 모듈을 추가
- 비즈니스 로직: `apps/api/app/services/`
- DB 모델/레포지토리: `apps/api/app/models.py`, `apps/api/app/repositories/`
- 프론트엔드: `apps/web/src/`
- 마이그레이션: `apps/api/alembic/`
- WFS 카탈로그: `resources/wfs/`
- 수동 수집 도구: `tools/collectors/`

## 9) WFS 카탈로그 엑셀 교체

- 기본 파일: `resources/wfs/브이월드_WFS_컬럼정보.xlsx`
- Docker API 컨테이너 경로: `/workspace/resources/wfs/브이월드_WFS_컬럼정보.xlsx`
- Docker 실행에서는 프로젝트 루트가 bind mount되므로, 같은 파일명으로 덮어쓰면 컨테이너 재빌드 없이 다음 `/wfs/layers` 조회부터 반영됩니다.
- 파일명을 바꾸면 `WFS_CATALOG_PATH`도 바꿔야 하며, API 컨테이너를 재시작해야 합니다.
- 필수 컬럼: `WFS명`, `WFS 한글명`, `컬럼명(영문)`, `컬럼명(한글)`
- 위 컬럼명이 바뀌거나 빠지면 WFS 레이어 목록 조회와 수집 시작이 실패합니다.

## 10) 품질 체크

```bash
# Python 테스트
uv run pytest -q

# Frontend 빌드
cd apps/web && npm run build
```

## 11) 운영 메모

- Upload에서 자동 변환이 실행되며 CSV/Excel은 위경도 컬럼 지정 후 변환됨
- WFS 수집도 백그라운드 Job으로 실행되며 WFS 탭에서 중단 요청 가능
- VWorld API 키는 UI 입력 시 서버에서 암호화되어 `app_secrets` 테이블에 저장됨
- `.env`의 `VWORLD_API_KEY`가 있으면 해당 키를 우선 사용
- 지도 렌더링은 선택한 `display rows`에 따라 성능이 크게 달라짐
- `rawdata/`, `data/`는 운영 데이터 경로이므로 백업 정책 필요
