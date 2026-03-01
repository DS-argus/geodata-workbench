from __future__ import annotations

from pathlib import Path

from app.services.storage_service import allocate_output_path, allocate_upload_path, ensure_storage_dirs


def test_ensure_storage_dirs_creates_missing_dirs(tmp_path: Path) -> None:
    raw = tmp_path / "rawdata"
    data = tmp_path / "data"

    ensure_storage_dirs(raw, data)

    assert raw.exists()
    assert data.exists()


def test_allocate_upload_path_sanitizes_spaces(tmp_path: Path) -> None:
    path = allocate_upload_path(tmp_path, "my file.csv")

    assert path.parent == tmp_path
    assert "my_file.csv" in path.name


def test_allocate_output_path_sets_extension(tmp_path: Path) -> None:
    path = allocate_output_path(tmp_path, "dataset", "gpkg")

    assert path.parent == tmp_path
    assert path.suffix == ".gpkg"
