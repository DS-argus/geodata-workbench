from __future__ import annotations

import argparse
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

Mode = Literal["docker", "local-pg", "local-lite"]
MODES: tuple[Mode, ...] = ("docker", "local-pg", "local-lite")
ESSENTIAL_KEYS: tuple[str, ...] = (
    "DATABASE_URL",
    "PROJECT_ROOT",
    "VWORLD_API_KEY",
    "APP_ENCRYPTION_KEY",
    "WFS_CATALOG_PATH",
)
MODE_DATABASE_URLS: dict[Mode, str] = {
    "docker": "postgresql+psycopg://postgres:postgres@db:5432/geodata",
    "local-pg": "postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
    "local-lite": "sqlite:///./data/geodata-lite.db",
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
    postgres_local_5432: bool


def _is_local_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_environment(
    project_root: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    postgres_probe: Callable[[], bool] | None = None,
) -> EnvironmentDetection:
    root = project_root or Path.cwd()
    has_docker = which("docker") is not None
    has_docker_compose = has_docker or which("docker-compose") is not None
    has_compose_file = any((root / name).exists() for name in ("docker-compose.yml", "compose.yml", "compose.yaml"))

    if postgres_probe is None:
        postgres_probe = lambda: _is_local_port_open("localhost", 5432)

    return EnvironmentDetection(
        has_docker=has_docker,
        has_docker_compose=has_docker_compose,
        has_compose_file=has_compose_file,
        has_uv=which("uv") is not None,
        has_python=which("python") is not None or which("python3") is not None,
        has_node=which("node") is not None,
        has_npm=which("npm") is not None,
        postgres_local_5432=postgres_probe(),
    )


def recommend_mode(env: EnvironmentDetection) -> tuple[Mode, str]:
    if env.has_docker and env.has_docker_compose and env.has_compose_file:
        return "docker", "Docker + compose are available and this repo includes a compose file."
    if env.postgres_local_5432 and env.has_python:
        return "local-pg", "Local PostgreSQL appears reachable on localhost:5432."
    return "local-lite", "No local PostgreSQL detected; local-lite avoids external DB setup."


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


def render_env_content(template_text: str, existing_text: str, mode: Mode) -> str:
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

    for key in ESSENTIAL_KEYS:
        merged.setdefault(key, "")

    merged["DATABASE_URL"] = MODE_DATABASE_URLS[mode]

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

    return "\n".join(f"{key}={merged[key]}" for key in output_order) + "\n"


def update_env_file(project_root: Path, mode: Mode) -> Path:
    template_path = project_root / ".env.example"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing .env.example at {template_path}")

    env_path = project_root / ".env"
    template_text = template_path.read_text(encoding="utf-8")
    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    rendered = render_env_content(template_text=template_text, existing_text=existing_text, mode=mode)
    env_path.write_text(rendered, encoding="utf-8")
    return env_path


def preview_env_update(project_root: Path, mode: Mode) -> Path:
    template_path = project_root / ".env.example"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing .env.example at {template_path}")
    return project_root / ".env"


def _print_detection(env: EnvironmentDetection) -> None:
    def status(value: bool) -> str:
        return "yes" if value else "no"

    print("Detected environment:")
    print(f"  docker: {status(env.has_docker)}")
    print(f"  docker compose: {status(env.has_docker_compose)}")
    print(f"  compose file: {status(env.has_compose_file)}")
    print(f"  uv: {status(env.has_uv)}")
    print(f"  python: {status(env.has_python)}")
    print(f"  node: {status(env.has_node)}")
    print(f"  npm: {status(env.has_npm)}")
    print(f"  localhost:5432 open: {status(env.postgres_local_5432)}")


def _prompt_mode(recommended: Mode) -> Mode:
    label = "/".join(MODES)
    lookup = {"1": "docker", "2": "local-pg", "3": "local-lite"}

    print("\nSelect setup mode:")
    print(f"  1) docker (recommended: {'yes' if recommended == 'docker' else 'no'})")
    print(f"  2) local-pg (recommended: {'yes' if recommended == 'local-pg' else 'no'})")
    print(f"  3) local-lite (recommended: {'yes' if recommended == 'local-lite' else 'no'})")

    while True:
        raw = input(f"Mode [{label}] (default: {recommended}): ").strip().lower()
        if not raw:
            return recommended
        if raw in lookup:
            return lookup[raw]  # type: ignore[return-value]
        if raw in MODES:
            return raw  # type: ignore[return-value]
        print("Invalid choice. Please select docker, local-pg, local-lite, or 1/2/3.")


def _print_next_steps(mode: Mode) -> None:
    next_steps: dict[Mode, list[str]] = {
        "docker": [
            "docker compose up -d --build",
            "docker compose ps",
            "open http://localhost:5173",
        ],
        "local-pg": [
            "docker compose up -d db",
            "uv sync",
            "uv run alembic upgrade head",
            "uv run uvicorn app.api:app --reload --port 8000",
            "cd apps/web && npm install && npm run dev",
        ],
        "local-lite": [
            "uv sync",
            "uv run uvicorn app.api:app --reload --port 8000",
            "cd apps/web && npm install && npm run dev",
        ],
    }

    print("\nNext steps:")
    for step in next_steps[mode]:
        print(f"  {step}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Setup helper for geodata-dashboard")
    parser.add_argument("--mode", choices=MODES, help="Setup mode")
    parser.add_argument("--yes", action="store_true", help="Run non-interactively using --mode or recommendation")
    parser.add_argument("--dry-run", action="store_true", help="Preview setup result without writing .env")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path.cwd()

    env = detect_environment(project_root=project_root)
    recommended, reason = recommend_mode(env)

    _print_detection(env)
    print(f"\nRecommended mode: {recommended} ({reason})")

    selected: Mode
    if args.mode:
        selected = args.mode
        print(f"Using explicit mode: {selected}")
    elif args.yes or not sys.stdin.isatty():
        selected = recommended
        print(f"Using recommended mode automatically: {selected}")
    else:
        selected = _prompt_mode(recommended)

    if args.dry_run:
        env_path = preview_env_update(project_root=project_root, mode=selected)
        print(f"\n[DRY-RUN] {env_path} would be updated (DATABASE_URL -> {MODE_DATABASE_URLS[selected]})")
        print("[DRY-RUN] .env file has not been changed.")
    else:
        env_path = update_env_file(project_root=project_root, mode=selected)
        print(f"\nUpdated {env_path} (DATABASE_URL -> {MODE_DATABASE_URLS[selected]})")

    _print_next_steps(selected)
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
