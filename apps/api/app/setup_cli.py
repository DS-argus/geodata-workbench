from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import quote

Mode = Literal["docker", "local-pg"]
MODES: tuple[Mode, ...] = ("docker", "local-pg")
POSTGRES_KEYS: tuple[str, ...] = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_ADMIN_DB",
)
ESSENTIAL_KEYS: tuple[str, ...] = (
    *POSTGRES_KEYS,
    "DATABASE_URL",
    "PROJECT_ROOT",
    "VWORLD_API_KEY",
    "APP_ENCRYPTION_KEY",
    "WFS_CATALOG_PATH",
)
TEMPLATE_SYNC_KEYS: tuple[str, ...] = (
    "WFS_CATALOG_PATH",
)
MODE_DATABASE_URLS: dict[Mode, str] = {
    "docker": "postgresql+psycopg://postgres:postgres@db:5432/geodata",
    "local-pg": "postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
}
MODE_POSTGRES_DEFAULTS: dict[Mode, dict[str, str]] = {
    "docker": {
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "geodata",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "POSTGRES_ADMIN_DB": "postgres",
    },
    "local-pg": {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "geodata",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "POSTGRES_ADMIN_DB": "postgres",
    },
}
REQUIREMENT_GUIDANCE: dict[str, str] = {
    "docker": "Docker Desktop 또는 Docker Engine을 설치하고 'docker --version'이 동작하는지 확인하세요.",
    "docker compose": "Docker Compose를 사용할 수 있어야 합니다. 'docker compose version'을 확인하세요.",
    "docker-compose.yml": "프로젝트 루트에서 실행 중인지, docker-compose.yml 파일이 있는지 확인하세요.",
    "uv": "uv를 설치하고 새 PowerShell/터미널에서 'uv --version'이 동작하는지 확인하세요.",
    "node": "Node.js LTS를 설치하고 새 PowerShell/터미널에서 'node --version'이 동작하는지 확인하세요.",
    "npm": "Node.js 설치 후 새 PowerShell/터미널에서 'npm --version'이 동작하는지 확인하세요.",
}


@dataclass(frozen=True)
class EnvironmentDetection:
    has_docker: bool
    has_docker_compose: bool
    has_compose_file: bool
    has_uv: bool
    has_python: bool
    has_node: bool
    has_npm: bool
    postgres_port_open: bool
    is_windows: bool


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    admin_database: str


def _log(message: str) -> None:
    print(f"[setup] {message}")


def _status(value: bool) -> str:
    return "확인" if value else "없음"


def _format_requirement_guidance(missing: list[str]) -> str:
    lines = ["해야 할 일:"]
    for item in missing:
        if item.startswith("local PostgreSQL on "):
            endpoint = item.removeprefix("local PostgreSQL on ")
            help_text = (
                f"PostgreSQL/PostGIS를 {endpoint}에서 실행하고 "
                "POSTGRES_USER/POSTGRES_PASSWORD 값으로 접속할 수 있게 준비하세요."
            )
        else:
            help_text = REQUIREMENT_GUIDANCE.get(item, f"{item} 항목을 준비하세요.")
        lines.append(f"  - {help_text}")
    lines.append("준비가 끝나면 setup 명령을 다시 실행하세요.")
    return "\n".join(lines)


def _is_local_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _command_succeeds(command: list[str], timeout: float = 5.0) -> bool:
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _has_docker_compose(which: Callable[[str], str | None], command_succeeds: Callable[[list[str]], bool]) -> bool:
    if which("docker") is not None and command_succeeds(["docker", "compose", "version"]):
        return True
    if which("docker-compose") is not None and command_succeeds(["docker-compose", "version"]):
        return True
    return False


def detect_environment(
    project_root: Path | None = None,
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    which: Callable[[str], str | None] = shutil.which,
    postgres_probe: Callable[[], bool] | None = None,
    command_succeeds: Callable[[list[str]], bool] = _command_succeeds,
) -> EnvironmentDetection:
    root = project_root or Path.cwd()
    has_docker = which("docker") is not None
    has_docker_compose = _has_docker_compose(which=which, command_succeeds=command_succeeds)
    has_compose_file = any((root / name).exists() for name in ("docker-compose.yml", "compose.yml", "compose.yaml"))

    if postgres_probe is None:
        def postgres_probe() -> bool:
            return _is_local_port_open(postgres_host, postgres_port)

    return EnvironmentDetection(
        has_docker=has_docker,
        has_docker_compose=has_docker_compose,
        has_compose_file=has_compose_file,
        has_uv=which("uv") is not None,
        has_python=which("python") is not None or which("python3") is not None,
        has_node=which("node") is not None,
        has_npm=which("npm") is not None,
        postgres_port_open=postgres_probe(),
        is_windows=sys.platform.startswith("win"),
    )


def recommend_mode(env: EnvironmentDetection) -> tuple[Mode, str]:
    if env.is_windows:
        return "local-pg", "Windows에서는 로컬 PostgreSQL과 로컬 Node/npm 실행을 사용합니다."
    return "docker", "macOS/Linux에서는 Docker Compose로 API, Web, PostgreSQL을 함께 실행합니다."


def allowed_modes(env: EnvironmentDetection) -> tuple[Mode, ...]:
    if env.is_windows:
        return ("local-pg",)
    return ("docker",)


def validate_mode_allowed(env: EnvironmentDetection, mode: Mode) -> None:
    if mode in allowed_modes(env):
        return
    if mode == "docker":
        raise RuntimeError("Windows에서는 local-pg 모드만 사용합니다. 'pwsh ./setup.ps1'로 실행하세요.")
    raise RuntimeError("local-pg 설정은 Windows 전용입니다. macOS/Linux에서는 Docker Compose만 사용하세요.")


def _parse_env_lines(text: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        items.append((key, value.strip()))
    return items


def _parse_postgres_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError(f"POSTGRES_PORT 값이 숫자가 아닙니다: {value}") from exc
    if port < 1 or port > 65535:
        raise RuntimeError(f"POSTGRES_PORT 값은 1-65535 범위여야 합니다: {value}")
    return port


def _database_url(settings: PostgresSettings, database: str | None = None) -> str:
    user = quote(settings.user, safe="")
    password = quote(settings.password, safe="")
    host = settings.host
    db_name = quote(database or settings.database, safe="")
    return f"postgresql+psycopg://{user}:{password}@{host}:{settings.port}/{db_name}"


def _psycopg_url(settings: PostgresSettings, database: str | None = None) -> str:
    user = quote(settings.user, safe="")
    password = quote(settings.password, safe="")
    host = settings.host
    db_name = quote(database or settings.database, safe="")
    return f"postgresql://{user}:{password}@{host}:{settings.port}/{db_name}"


def _postgres_settings_from_values(values: dict[str, str]) -> PostgresSettings:
    missing = [key for key in POSTGRES_KEYS if not values.get(key)]
    if missing:
        raise RuntimeError(
            f".env에 PostgreSQL 설정값이 비어 있습니다: {', '.join(missing)}\n\n"
            "해야 할 일:\n"
            "  - .env의 POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, "
            "POSTGRES_PASSWORD, POSTGRES_ADMIN_DB 값을 채우세요.\n"
            "준비가 끝나면 setup 명령을 다시 실행하세요."
        )
    return PostgresSettings(
        host=values["POSTGRES_HOST"],
        port=_parse_postgres_port(values["POSTGRES_PORT"]),
        database=values["POSTGRES_DB"],
        user=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"],
        admin_database=values["POSTGRES_ADMIN_DB"],
    )


def _merge_env_values(
    template_text: str,
    existing_text: str,
    mode: Mode,
    pg_port: int | None = None,
) -> tuple[dict[str, str], list[str], PostgresSettings]:
    template_items = _parse_env_lines(template_text)
    existing_items = _parse_env_lines(existing_text)

    merged: dict[str, str] = {key: value for key, value in template_items}
    template_order: list[str] = []
    existing_order: list[str] = []

    for key, _ in template_items:
        if key not in template_order:
            template_order.append(key)

    for key, value in existing_items:
        merged[key] = value
        if key not in existing_order:
            existing_order.append(key)

    template_defaults = {key: value for key, value in template_items}
    for key in TEMPLATE_SYNC_KEYS:
        if key in template_defaults:
            merged[key] = template_defaults[key]

    defaults = MODE_POSTGRES_DEFAULTS[mode]
    merged["POSTGRES_HOST"] = defaults["POSTGRES_HOST"]
    for key in ("POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_DB"):
        if not merged.get(key):
            merged[key] = defaults[key]
    if pg_port is not None:
        merged["POSTGRES_PORT"] = str(pg_port)

    for key in ESSENTIAL_KEYS:
        merged.setdefault(key, "")

    postgres_settings = _postgres_settings_from_values(merged)
    merged["DATABASE_URL"] = _database_url(postgres_settings)

    output_order: list[str] = []
    for key in template_order:
        if key not in output_order:
            output_order.append(key)

    for key in ESSENTIAL_KEYS:
        if key not in output_order:
            output_order.append(key)

    for key in existing_order:
        if key not in output_order:
            output_order.append(key)

    for key in merged:
        if key not in output_order:
            output_order.append(key)

    return merged, output_order, postgres_settings


def render_env_content(
    template_text: str,
    existing_text: str,
    mode: Mode,
    pg_port: int | None = None,
) -> str:
    merged, output_order, _ = _merge_env_values(
        template_text=template_text,
        existing_text=existing_text,
        mode=mode,
        pg_port=pg_port,
    )
    return "\n".join(f"{key}={merged[key]}" for key in output_order) + "\n"


def resolve_postgres_settings(project_root: Path, mode: Mode, pg_port: int | None = None) -> PostgresSettings:
    template_path = project_root / ".env.example"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing .env.example at {template_path}")

    env_path = project_root / ".env"
    template_text = template_path.read_text(encoding="utf-8")
    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    _, _, postgres_settings = _merge_env_values(
        template_text=template_text,
        existing_text=existing_text,
        mode=mode,
        pg_port=pg_port,
    )
    return postgres_settings


def update_env_file(project_root: Path, mode: Mode, pg_port: int | None = None) -> Path:
    template_path = project_root / ".env.example"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing .env.example at {template_path}")

    env_path = project_root / ".env"
    template_text = template_path.read_text(encoding="utf-8")
    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    rendered = render_env_content(template_text=template_text, existing_text=existing_text, mode=mode, pg_port=pg_port)
    env_path.write_text(rendered, encoding="utf-8")
    return env_path


def preview_env_update(project_root: Path, mode: Mode) -> Path:
    template_path = project_root / ".env.example"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing .env.example at {template_path}")
    return project_root / ".env"


def ensure_local_database(settings: PostgresSettings) -> str:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL 데이터베이스를 준비하려면 psycopg가 필요합니다.\n\n"
            "해야 할 일:\n"
            "  - 먼저 'uv sync'를 실행한 뒤 setup을 다시 실행하세요."
        ) from exc

    admin_url = _psycopg_url(settings, database=settings.admin_database)
    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.database,))
                if cur.fetchone():
                    _log(f"PostgreSQL 데이터베이스 확인 완료: {settings.database}")
                    return "exists"
                _log(f"PostgreSQL 데이터베이스를 생성합니다: {settings.database}")
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.database)))
                _log(f"PostgreSQL 데이터베이스 생성 완료: {settings.database}")
                return "created"
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL 데이터베이스를 준비하지 못했습니다.\n\n"
            "해야 할 일:\n"
            f"  - PostgreSQL이 {settings.host}:{settings.port}에서 실행 중인지 확인하세요.\n"
            f"  - .env의 POSTGRES_USER/POSTGRES_PASSWORD가 {settings.admin_database} DB에 접속 가능한지 확인하세요.\n"
            f"  - {settings.database} DB가 없다면 해당 사용자에게 CREATE DATABASE 권한이 있어야 합니다.\n"
            f"  - 직접 만들려면 psql에서 'CREATE DATABASE {settings.database};'를 실행하세요.\n"
            f"\n원인: {exc}"
        ) from exc


def _print_detection(env: EnvironmentDetection, postgres_host: str, postgres_port: int) -> None:
    print("감지한 실행 환경:")
    print(f"  docker: {_status(env.has_docker)}")
    print(f"  docker compose: {_status(env.has_docker_compose)}")
    print(f"  compose file: {_status(env.has_compose_file)}")
    print(f"  uv: {_status(env.has_uv)}")
    print(f"  python: {_status(env.has_python)}")
    print(f"  node: {_status(env.has_node)}")
    print(f"  npm: {_status(env.has_npm)}")
    print(f"  {postgres_host}:{postgres_port} open: {_status(env.postgres_port_open)}")
    print(f"  windows: {_status(env.is_windows)}")


def _prompt_mode(recommended: Mode) -> Mode:
    label = "/".join(MODES)
    lookup = {"1": "docker", "2": "local-pg"}

    print("\n설정 모드를 선택하세요:")
    print(f"  1) docker - macOS/Linux 컨테이너 모드 (추천: {'예' if recommended == 'docker' else '아니오'})")
    print(f"  2) local-pg - Windows 로컬 PostgreSQL 모드 (추천: {'예' if recommended == 'local-pg' else '아니오'})")

    while True:
        raw = input(f"모드 [{label}] (기본값: {recommended}): ").strip().lower()
        if not raw:
            return recommended
        if raw in lookup:
            return lookup[raw]  # type: ignore[return-value]
        if raw in MODES:
            return raw  # type: ignore[return-value]
        print("잘못된 선택입니다. docker, local-pg, 1, 2 중 하나를 입력하세요.")


def _port_arg(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("포트는 숫자여야 합니다.") from exc
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("포트는 1-65535 범위여야 합니다.")
    return port


def validate_mode(env: EnvironmentDetection, mode: Mode, postgres_host: str = "localhost", postgres_port: int = 5432) -> None:
    validate_mode_allowed(env, mode)

    if mode == "docker":
        missing = []
        if not env.has_docker:
            missing.append("docker")
        if not env.has_docker_compose:
            missing.append("docker compose")
        if not env.has_compose_file:
            missing.append("docker-compose.yml")
        if missing:
            raise RuntimeError(
                f"Docker 설정에 필요한 항목이 없습니다: {', '.join(missing)}\n\n"
                f"{_format_requirement_guidance(missing)}"
            )
        return

    if mode == "local-pg":
        missing = []
        if not env.has_uv:
            missing.append("uv")
        if not env.has_node:
            missing.append("node")
        if not env.has_npm:
            missing.append("npm")
        if not env.postgres_port_open:
            missing.append(f"local PostgreSQL on {postgres_host}:{postgres_port}")
        if missing:
            raise RuntimeError(
                f"Windows 로컬 설정에 필요한 항목이 없습니다: {', '.join(missing)}\n\n"
                f"{_format_requirement_guidance(missing)}"
            )


def _print_next_steps(mode: Mode) -> None:
    next_steps: dict[Mode, list[str]] = {
        "docker": [
            "docker compose up -d --build",
            "docker compose ps",
            "open http://localhost:5173",
        ],
        "local-pg": [
            "uv sync",
            "uv run alembic -c apps/api/alembic.ini upgrade head",
            "uv run uvicorn app.api:app --reload --port 8000",
            "cd apps/web && npm install && npm run dev",
        ],
    }

    print("\n다음 작업:")
    print("  아래 명령을 순서대로 실행하세요.")
    for step in next_steps[mode]:
        print(f"  {step}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Setup helper for geodata-workbench")
    parser.add_argument("--mode", choices=MODES, help="Setup mode")
    parser.add_argument(
        "--pg-port",
        "--port",
        dest="pg_port",
        type=_port_arg,
        default=5432,
        help="Local PostgreSQL port for local-pg mode (default: 5432)",
    )
    parser.add_argument("--yes", action="store_true", help="Run non-interactively using --mode or recommendation")
    parser.add_argument("--dry-run", action="store_true", help="Preview setup result without writing .env")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path.cwd()
    postgres_host = "localhost"
    postgres_port = args.pg_port

    _log(f"프로젝트 루트: {project_root}")
    _log(f"PostgreSQL 접속 포트: {postgres_port}")
    _log("실행 환경을 확인합니다.")
    env = detect_environment(project_root=project_root, postgres_host=postgres_host, postgres_port=postgres_port)
    recommended, reason = recommend_mode(env)
    permitted_modes = allowed_modes(env)

    _print_detection(env, postgres_host=postgres_host, postgres_port=postgres_port)
    print(f"\n추천 모드: {recommended} ({reason})")

    selected: Mode
    if args.mode:
        selected = args.mode
        _log(f"명시된 모드를 사용합니다: {selected}")
    elif len(permitted_modes) == 1:
        selected = permitted_modes[0]
        _log(f"현재 OS에서는 {selected} 모드만 사용합니다.")
    elif args.yes or not sys.stdin.isatty():
        selected = recommended
        _log(f"추천 모드를 자동으로 사용합니다: {selected}")
    else:
        selected = _prompt_mode(recommended)
        _log(f"선택된 모드: {selected}")

    validate_mode_allowed(env, selected)

    if args.dry_run:
        _log(".env 변경 미리보기를 수행합니다. 실제 파일은 수정하지 않습니다.")
        env_path = preview_env_update(project_root=project_root, mode=selected)
        postgres_settings = resolve_postgres_settings(project_root=project_root, mode=selected, pg_port=postgres_port)
        print(f"\n[DRY-RUN] {env_path} 파일이 갱신될 예정입니다.")
        print(f"[DRY-RUN] POSTGRES_PORT -> {postgres_settings.port}")
        print(f"[DRY-RUN] POSTGRES_DB -> {postgres_settings.database}")
        print(f"[DRY-RUN] DATABASE_URL -> {_database_url(postgres_settings)}")
        if selected == "local-pg":
            print(f"[DRY-RUN] {postgres_settings.database} DB가 없으면 생성할 예정입니다.")
        print("[DRY-RUN] .env 파일은 변경하지 않았습니다.")
    else:
        _log("선택한 모드에 필요한 항목을 검증합니다.")
        validate_mode(env, selected, postgres_host=postgres_host, postgres_port=postgres_port)
        _log(".env 파일을 생성 또는 갱신합니다.")
        postgres_settings = resolve_postgres_settings(project_root=project_root, mode=selected, pg_port=postgres_port)
        env_path = update_env_file(project_root=project_root, mode=selected, pg_port=postgres_port)
        print(f"\n.env 갱신 완료: {env_path}")
        print(f"POSTGRES_PORT -> {postgres_settings.port}")
        print(f"POSTGRES_DB -> {postgres_settings.database}")
        print(f"DATABASE_URL -> {_database_url(postgres_settings)}")
        if selected == "local-pg":
            _log("PostgreSQL 데이터베이스 존재 여부를 확인합니다.")
            ensure_local_database(postgres_settings)

    _print_next_steps(selected)
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        print("\n[setup] 설정을 취소했습니다.")
        return 130
    except FileNotFoundError as exc:
        print(f"\n[setup] 설정 실패: {exc}")
        print("\n해야 할 일:")
        print("  - 프로젝트 루트에서 setup 명령을 실행했는지 확인하세요.")
        print("  - .env.example 파일이 삭제되었다면 저장소에서 복구하세요.")
        print("준비가 끝나면 setup 명령을 다시 실행하세요.")
        return 2
    except RuntimeError as exc:
        print(f"\n[setup] 설정 실패:\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
