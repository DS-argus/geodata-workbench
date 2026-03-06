# Geodata Workbench 운영/개발 가이드

이 문서는 운영자/개발자를 위한 기술 문서입니다.  
일반 사용자 안내는 `README.md`를 참고하세요.

## 1) 아키텍처 개요

- `web` (`apps/web`): React + Vite UI (포트 5173)
- `api` (`app`): FastAPI 백엔드 (포트 8000)
- `db`: PostgreSQL + PostGIS (포트 5432)
- 원본 파일 저장: `rawdata/`
- 변환 결과 저장: `data/`
- DB에는 메타데이터(`files`, `jobs`, `datasets`, `app_secrets`)만 저장, 공간 본문은 파일로 저장

## 2) Setup 기반 초기화 (권장)

초기 설치/모드 설정은 `./setup`을 기본 진입점으로 사용합니다.

```bash
./setup
```

비대화형 예시:

```bash
./setup --mode docker --yes
./setup --mode local-pg --yes
./setup --mode local-lite --yes
```

## 3) 실행 모드 가이드

- `docker`: 팀 표준/운영 유사 환경이 필요할 때 (권장)
- `local-pg`: Docker 없이 개발하고, 로컬 PostgreSQL(PostGIS) 준비가 되어 있을 때
- `local-lite`: PostgreSQL 없이 빠른 확인/개발이 필요할 때 (SQLite)

SQLite(`local-lite`)는 현재 개발/검증 편의 모드입니다.  
향후 PostGIS 의존 기능이 추가되면 일부 기능이 제한될 수 있습니다.

## 4) setup 후 실행 명령 (요약)

### docker 모드

```bash
docker compose up -d --build
```

### local-pg / local-lite 모드

```bash
# API
uv run uvicorn app.api:app --reload --port 8000

# Web
cd apps/web
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

- Docker에서 `api` 컨테이너 시작 시 `alembic upgrade head` 자동 실행
- 로컬 개발(직접 `uvicorn` 실행) 시에는 수동 실행 필요

```bash
uv run alembic upgrade head
```

마이그레이션 생성(스키마 변경 시):

```bash
uv run alembic revision -m "설명"
```

## 7) 로컬 개발 (수동 경로, 필요 시)

```bash
# DB만 컨테이너로 실행
docker compose up -d db

# Backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.api:app --reload --port 8000

# Frontend
cd apps/web
npm install
npm run dev
```

## 8) 주요 경로

- 백엔드 API 엔트리: `app/api.py`
- 비즈니스 로직: `app/services/`
- DB 모델/레포지토리: `app/models.py`, `app/repositories/`
- 프론트엔드: `apps/web/src/`
- 마이그레이션: `alembic/`

## 9) 품질 체크

```bash
# Python 테스트
uv run pytest -q

# Frontend 빌드
cd apps/web && npm run build
```

## 10) 운영 메모

- Upload에서 자동 변환이 실행되며 CSV/Excel은 위경도 컬럼 지정 후 변환됨
- WFS 수집도 백그라운드 Job으로 실행되며 WFS 탭에서 중단 요청 가능
- VWorld API 키는 UI 입력 시 서버에서 암호화되어 `app_secrets` 테이블에 저장됨
- `.env`의 `VWORLD_API_KEY`가 있으면 해당 키를 우선 사용
- 지도 렌더링은 선택한 `display rows`에 따라 성능이 크게 달라짐
- `rawdata/`, `data/`는 운영 데이터 경로이므로 백업 정책 필요
