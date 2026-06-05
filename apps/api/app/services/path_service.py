from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def resolve_record_path(path_value: str, *, category_hint: str | None = None) -> Path:
    """
    Resolve a DB-stored path to the current runtime filesystem.

    This supports environment switches between local host paths and container paths
    by remapping suffixes under /rawdata/ or /data/ to the current PROJECT_ROOT.
    """
    settings = get_settings()
    path = Path(path_value)

    if path.exists():
        return path

    if not path.is_absolute():
        candidate = (settings.project_root / path).resolve()
        if candidate.exists():
            return candidate

    normalized = str(path_value).replace("\\", "/")
    mappings = [
        ("rawdata", settings.rawdata_dir),
        ("data", settings.data_dir),
    ]
    for name, base_dir in mappings:
        token = f"/{name}/"
        if token not in normalized:
            continue
        suffix = normalized.split(token, 1)[1].lstrip("/")
        candidate = base_dir / suffix
        if candidate.exists():
            return candidate
        if category_hint == name:
            return candidate

    if category_hint == "rawdata":
        return settings.rawdata_dir / path.name
    if category_hint == "data":
        return settings.data_dir / path.name

    return path
