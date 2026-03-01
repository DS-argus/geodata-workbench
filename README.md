# Geodata Dashboard

공간데이터를 로컬에서 업로드하고 변환한 뒤 지도에서 바로 확인하는 Streamlit 앱입니다.

## 빠른 시작

1. DB 실행

```bash
docker compose up -d db
```

2. 의존성 설치

```bash
uv sync
```

3. 마이그레이션 적용

```bash
uv run alembic upgrade head
```

4. 앱 실행

```bash
uv run streamlit run app/main.py
```

브라우저에서 `http://localhost:8501` 접속.

## 탭별 사용 가이드

### 1) Upload

1. `Upload files or a folder`에서 파일 또는 폴더를 선택합니다.
2. 필요하면 파일 이름(표시용)을 입력합니다.
3. `Save uploads`를 눌러 저장합니다.
4. 아래 `업로드 목록`에서 저장된 항목을 확인/삭제합니다.

지원 입력:
- 공간데이터 구성 파일이 포함된 **폴더 또는 ZIP**
- 위도/경도 컬럼이 포함된 **CSV 또는 Excel(`.xlsx`, `.xls`)**

참고:
- 폴더/ZIP은 Shapefile 기준 `.shp`, `.dbf`, `.shx`(권장 `.prj`)가 같은 데이터셋 단위로 포함되어야 합니다.
- CSV/Excel은 `Browse Directory`가 아니라 **직접 드래그앤드롭(또는 Browse files)** 으로 업로드하세요.

### 2) Convert

1. `Input file`에서 업로드된 원본을 선택합니다.
2. `Output format`에서 `geoparquet` 또는 `gpkg`를 선택합니다.
3. `CRS handling`을 선택합니다.
   - `Keep input CRS`: 원본 CRS 유지
   - `Transform to target CRS`: 원하는 CRS로 변환
4. CSV/Excel은 위도/경도 컬럼과 입력 CRS를 지정합니다.
5. `Run conversion`을 실행합니다.
6. 아래 `변환 데이터 목록`에서 결과 확인/삭제합니다.

### 3) Browse & Map

1. 상단에서 시각화할 파일(변환 결과)을 선택합니다.
2. `display rows`로 지도에 렌더링할 행 수를 조절합니다.
3. 하단 좌측에서 속성 미리보기(최대 10행), 우측에서 지도 확인합니다.
4. 지도에서 객체 hover 시 컬럼 속성 툴팁을 볼 수 있습니다.

## 참고

- 업로드 원본은 `rawdata/`, 변환 결과는 `data/`에 저장됩니다.
- 지도 렌더링 시 내부적으로 EPSG:4326 기준으로 표시됩니다.
- 업로드 용량 제한은 `.streamlit/config.toml`에서 설정합니다.
