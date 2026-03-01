from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.repositories import create_file


def _safe_relative_path(relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    parts = [part for part in Path(normalized).parts if part not in ("", ".", "..")]
    return Path(*parts) if parts else Path("uploaded_file")


def _deduplicate_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _write_stream(file_obj: BinaryIO, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_obj.seek(0)
    with output_path.open("wb") as out_file:
        shutil.copyfileobj(file_obj, out_file)
    return output_path.stat().st_size


def save_uploaded_file(
    session: Session,
    *,
    uploaded_name: str,
    display_name: str,
    file_obj: BinaryIO,
    rawdata_dir: Path,
) -> int:
    safe_name = _safe_relative_path(uploaded_name).name
    output_path = _deduplicate_path(rawdata_dir / safe_name)
    file_size = _write_stream(file_obj, output_path)

    extension = output_path.suffix.lower().lstrip(".") or "bin"
    record = create_file(
        session,
        category="raw",
        path=str(output_path),
        name=display_name,
        format=extension,
        size_bytes=file_size,
    )
    return record.id


def save_uploaded_folder(
    session: Session,
    *,
    folder_name: str,
    file_entries: Iterable[tuple[BinaryIO, str]],
    rawdata_dir: Path,
) -> int:
    safe_folder_name = _safe_relative_path(folder_name).name
    folder_path = _deduplicate_path(rawdata_dir / safe_folder_name)
    folder_path.mkdir(parents=True, exist_ok=True)

    total_size = 0
    file_count = 0
    for file_obj, relative_path in file_entries:
        safe_rel_path = _safe_relative_path(relative_path)
        output_path = folder_path / safe_rel_path
        total_size += _write_stream(file_obj, output_path)
        file_count += 1

    if file_count == 0:
        raise ValueError("Folder upload did not include any files.")

    record = create_file(
        session,
        category="raw",
        path=str(folder_path),
        name=safe_folder_name,
        format="folder",
        size_bytes=total_size,
    )
    return record.id
