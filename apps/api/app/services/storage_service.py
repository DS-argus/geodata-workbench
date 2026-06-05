from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SEOUL_TZ = ZoneInfo("Asia/Seoul")


def ensure_storage_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def allocate_upload_path(base_dir: Path, original_name: str) -> Path:
    timestamp = datetime.now(SEOUL_TZ).strftime("%Y%m%d_%H%M%S_%f")
    safe_name = original_name.replace(" ", "_")
    return base_dir / f"{timestamp}_{safe_name}"


def allocate_output_path(base_dir: Path, stem: str, extension: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(SEOUL_TZ).strftime("%Y%m%d_%H%M%S")
    candidate = base_dir / f"{stem}_{timestamp}.{extension}"
    if not candidate.exists():
        return candidate

    index = 1
    while True:
        next_candidate = base_dir / f"{stem}_{timestamp}_{index}.{extension}"
        if not next_candidate.exists():
            return next_candidate
        index += 1
