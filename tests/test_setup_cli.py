from __future__ import annotations

from pathlib import Path
import shutil
import uuid

import pytest

from app.setup_cli import (
    EnvironmentDetection,
    MODE_DATABASE_URLS,
    recommend_mode,
    render_env_content,
    run,
    update_env_file,
    validate_mode,
)


def test_recommend_mode_prefers_docker_when_available() -> None:
    env = EnvironmentDetection(
        has_docker=True,
        has_docker_compose=True,
        has_compose_file=True,
        has_uv=True,
        has_python=True,
        has_node=True,
        has_npm=True,
        postgres_port_open=True,
        is_windows=False,
    )

    mode, reason = recommend_mode(env)

    assert mode == "docker"
    assert "Docker" in reason


def test_recommend_mode_falls_back_to_local_pg_when_postgres_is_open() -> None:
    env = EnvironmentDetection(
        has_docker=False,
        has_docker_compose=False,
        has_compose_file=True,
        has_uv=True,
        has_python=True,
        has_node=False,
        has_npm=False,
        postgres_port_open=True,
        is_windows=True,
    )

    mode, _ = recommend_mode(env)

    assert mode == "local-pg"


def test_recommend_mode_uses_docker_on_non_windows_even_without_local_postgres() -> None:
    env = EnvironmentDetection(
        has_docker=False,
        has_docker_compose=False,
        has_compose_file=False,
        has_uv=True,
        has_python=True,
        has_node=False,
        has_npm=False,
        postgres_port_open=False,
        is_windows=False,
    )

    mode, _ = recommend_mode(env)

    assert mode == "docker"


def test_render_env_content_overrides_database_url_and_preserves_existing_values() -> None:
    template = "\n".join(
        [
            "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
            "POSTGRES_HOST=localhost",
            "POSTGRES_PORT=5432",
            "POSTGRES_DB=geodata",
            "POSTGRES_USER=postgres",
            "POSTGRES_PASSWORD=postgres",
            "POSTGRES_ADMIN_DB=postgres",
            "PROJECT_ROOT=.",
            "VWORLD_API_KEY=",
            "APP_ENCRYPTION_KEY=",
            "WFS_CATALOG_PATH=./resources/wfs/catalog.xlsx",
        ]
    )
    existing = "\n".join(
        [
            "DATABASE_URL=postgresql://old",
            "VWORLD_API_KEY=already-set",
            "CUSTOM_FLAG=1",
        ]
    )

    rendered = render_env_content(template_text=template, existing_text=existing, mode="local-pg")

    lines = dict(line.split("=", 1) for line in rendered.strip().splitlines())
    assert lines["DATABASE_URL"] == MODE_DATABASE_URLS["local-pg"]
    assert lines["VWORLD_API_KEY"] == "already-set"
    assert lines["PROJECT_ROOT"] == "."
    assert lines["APP_ENCRYPTION_KEY"] == ""
    assert lines["CUSTOM_FLAG"] == "1"


def test_update_env_file_creates_or_updates_env_file() -> None:
    tmp_root = Path("tmp") / "test_setup_cli" / f"env-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        (tmp_root / ".env.example").write_text(
            "\n".join(
                [
                    "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
                    "POSTGRES_HOST=localhost",
                    "POSTGRES_PORT=5432",
                    "POSTGRES_DB=geodata",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=postgres",
                    "POSTGRES_ADMIN_DB=postgres",
                    "PROJECT_ROOT=.",
                    "VWORLD_API_KEY=",
                    "APP_ENCRYPTION_KEY=",
                    "WFS_CATALOG_PATH=./resources/wfs/catalog.xlsx",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_root / ".env").write_text("VWORLD_API_KEY=keep-me\n", encoding="utf-8")

        env_path = update_env_file(project_root=tmp_root, mode="docker")

        text = env_path.read_text(encoding="utf-8")
        lines = dict(line.split("=", 1) for line in text.strip().splitlines())

        assert lines["DATABASE_URL"] == MODE_DATABASE_URLS["docker"]
        assert lines["POSTGRES_HOST"] == "db"
        assert lines["POSTGRES_PORT"] == "5432"
        assert lines["VWORLD_API_KEY"] == "keep-me"
        assert lines["WFS_CATALOG_PATH"] == "./resources/wfs/catalog.xlsx"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_render_env_content_uses_explicit_postgres_port() -> None:
    template = "\n".join(
        [
            "POSTGRES_HOST=localhost",
            "POSTGRES_PORT=5432",
            "POSTGRES_DB=geodata",
            "POSTGRES_USER=postgres",
            "POSTGRES_PASSWORD=postgres",
            "POSTGRES_ADMIN_DB=postgres",
            "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
        ]
    )
    existing = "\n".join(
        [
            "POSTGRES_PORT=15432",
            "POSTGRES_PASSWORD=secret",
            "DATABASE_URL=postgresql://old",
        ]
    )

    rendered = render_env_content(template_text=template, existing_text=existing, mode="local-pg", pg_port=15433)

    lines = dict(line.split("=", 1) for line in rendered.strip().splitlines())
    assert lines["POSTGRES_HOST"] == "localhost"
    assert lines["POSTGRES_PORT"] == "15433"
    assert lines["POSTGRES_PASSWORD"] == "secret"
    assert lines["DATABASE_URL"] == "postgresql+psycopg://postgres:secret@localhost:15433/geodata"


def test_setup_dry_run_does_not_modify_env_file() -> None:
    tmp_root = (Path("tmp") / "test_setup_cli" / f"dryrun-{uuid.uuid4().hex}").resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    prev_cwd = Path.cwd()
    try:
        (tmp_root / ".env.example").write_text(
            "\n".join(
                [
                    "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
                    "POSTGRES_HOST=localhost",
                    "POSTGRES_PORT=5432",
                    "POSTGRES_DB=geodata",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=postgres",
                    "POSTGRES_ADMIN_DB=postgres",
                    "PROJECT_ROOT=.",
                    "VWORLD_API_KEY=",
                    "APP_ENCRYPTION_KEY=",
                    "WFS_CATALOG_PATH=./resources/wfs/catalog.xlsx",
                ]
            ),
            encoding="utf-8",
        )
        original_env = "\n".join(
            [
                "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
                "VWORLD_API_KEY=keep-me",
            ]
        )
        (tmp_root / ".env").write_text(original_env + "\n", encoding="utf-8")

        # run() uses current working directory as project root.
        import os

        os.chdir(tmp_root)
        exit_code = run(["--mode", "docker", "--yes", "--dry-run"])
        assert exit_code == 0

        current_env = (tmp_root / ".env").read_text(encoding="utf-8")
        assert current_env == original_env + "\n"
    finally:
        import os

        os.chdir(prev_cwd)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_validate_mode_reports_korean_guidance_for_missing_windows_requirements() -> None:
    env = EnvironmentDetection(
        has_docker=False,
        has_docker_compose=False,
        has_compose_file=True,
        has_uv=False,
        has_python=True,
        has_node=False,
        has_npm=False,
        postgres_port_open=False,
        is_windows=True,
    )

    with pytest.raises(RuntimeError) as exc_info:
        validate_mode(env, "local-pg", postgres_port=15432)

    message = str(exc_info.value)
    assert "Windows 로컬 설정에 필요한 항목이 없습니다" in message
    assert "해야 할 일" in message
    assert "uv --version" in message
    assert "node --version" in message
    assert "npm --version" in message
    assert "localhost:15432" in message
