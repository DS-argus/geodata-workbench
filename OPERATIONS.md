# Geodata Workbench 운영/개발 가이드

이 문서는 운영자/개발자를 위한 기술 문서입니다.  
일반 사용자 안내는 `README.md`를 참고하세요.

## 1) 아키텍처 개요

- `web` (`apps/web`): React + Vite UI (포트 5173)
- `api` (`app`): FastAPI 백엔드 (포트 8000)
- `db`: PostgreSQL + PostGIS (포트 5432)
- 원본 파일 저장: `rawdata/`
- 변환 결과 저장: `data/`
- DB에는 메타데이터(`files`, `jobs`, `datasets`)만 저장, 공간 본문은 파일로 저장

## 2) Docker 운영

### 전체 실행

```bash
docker compose up -d --build
```

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

## 3) DB 마이그레이션(Alembic)

현재 정책:

- Docker에서 `api` 컨테이너 시작 시 `alembic upgrade head` 자동 실행
- 로컬 개발(직접 `uvicorn` 실행) 시에는 수동 실행 필요

수동 실행:

```bash
uv run alembic upgrade head
```

마이그레이션 생성(스키마 변경 시):

```bash
uv run alembic revision -m "설명"
```

## 4) 로컬 개발 (선택)

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

## 5) 주요 경로

- 백엔드 API 엔트리: `app/api.py`
- 비즈니스 로직: `app/services/`
- DB 모델/레포지토리: `app/models.py`, `app/repositories/`
- 프론트엔드: `apps/web/src/`
- 마이그레이션: `alembic/`

## 6) 품질 체크

```bash
# Python 테스트
uv run pytest -q

# Frontend 빌드
cd apps/web && npm run build
```

## 7) 운영 메모

- 대용량 변환은 시간이 걸릴 수 있으며, Convert 탭에서 중단 요청 가능
- 지도 렌더링은 선택한 `display rows`에 따라 성능이 크게 달라짐
- `rawdata/`, `data/`는 운영 데이터 경로이므로 백업 정책 필요
