from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from app.setup_cli import (
    EnvironmentDetection,
    MODE_DATABASE_URLS,
    recommend_mode,
    render_env_content,
    run,
    update_env_file,
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
        postgres_local_5432=True,
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
        postgres_local_5432=True,
    )

    mode, _ = recommend_mode(env)

    assert mode == "local-pg"


def test_recommend_mode_uses_local_lite_without_postgres() -> None:
    env = EnvironmentDetection(
        has_docker=False,
        has_docker_compose=False,
        has_compose_file=False,
        has_uv=True,
        has_python=True,
        has_node=False,
        has_npm=False,
        postgres_local_5432=False,
    )

    mode, _ = recommend_mode(env)

    assert mode == "local-lite"


def test_render_env_content_overrides_database_url_and_preserves_existing_values() -> None:
    template = "\n".join(
        [
            "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
            "PROJECT_ROOT=.",
            "VWORLD_API_KEY=",
            "APP_ENCRYPTION_KEY=",
            "WFS_CATALOG_PATH=./wfs/catalog.xlsx",
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
                    "PROJECT_ROOT=.",
                    "VWORLD_API_KEY=",
                    "APP_ENCRYPTION_KEY=",
                    "WFS_CATALOG_PATH=./wfs/catalog.xlsx",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_root / ".env").write_text("VWORLD_API_KEY=keep-me\n", encoding="utf-8")

        env_path = update_env_file(project_root=tmp_root, mode="docker")

        text = env_path.read_text(encoding="utf-8")
        lines = dict(line.split("=", 1) for line in text.strip().splitlines())

        assert lines["DATABASE_URL"] == MODE_DATABASE_URLS["docker"]
        assert lines["VWORLD_API_KEY"] == "keep-me"
        assert lines["WFS_CATALOG_PATH"] == "./wfs/catalog.xlsx"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_setup_dry_run_does_not_modify_env_file() -> None:
    tmp_root = (Path("tmp") / "test_setup_cli" / f"dryrun-{uuid.uuid4().hex}").resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    prev_cwd = Path.cwd()
    try:
        (tmp_root / ".env.example").write_text(
            "\n".join(
                [
                    "DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
                    "PROJECT_ROOT=.",
                    "VWORLD_API_KEY=",
                    "APP_ENCRYPTION_KEY=",
                    "WFS_CATALOG_PATH=./wfs/catalog.xlsx",
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
        exit_code = run(["--mode", "local-lite", "--yes", "--dry-run"])
        assert exit_code == 0

        current_env = (tmp_root / ".env").read_text(encoding="utf-8")
        assert current_env == original_env + "\n"
    finally:
        import os

        os.chdir(prev_cwd)
        shutil.rmtree(tmp_root, ignore_errors=True)
