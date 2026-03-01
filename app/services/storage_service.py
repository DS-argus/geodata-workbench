from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_storage_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def allocate_upload_path(base_dir: Path, original_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = original_name.replace(" ", "_")
    return base_dir / f"{timestamp}_{safe_name}"


def allocate_output_path(base_dir: Path, stem: str, extension: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return base_dir / f"{stem}_{timestamp}.{extension}"
