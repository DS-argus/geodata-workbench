from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _like_to_regex(pattern: str) -> str:
    parts: list[str] = ["^"]
    for char in pattern:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    parts.append("$")
    return "".join(parts)


def _build_like_mask(values: pd.Series, query: str) -> pd.Series:
    q = query.strip()
    if not q:
        return pd.Series(True, index=values.index)

    pattern = q if ("%" in q or "_" in q) else f"%{q}%"
    regex = _like_to_regex(pattern)
    return values.fillna("").astype(str).str.contains(regex, case=False, regex=True)


def apply_list_query(
    df: pd.DataFrame,
    *,
    query: str,
    format_filter: list[str] | None,
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
    search_columns: tuple[str, ...] = ("name", "path"),
) -> tuple[pd.DataFrame, int, int]:
    filtered = df.copy()

    if query.strip():
        mask = pd.Series(False, index=filtered.index)
        for column in search_columns:
            if column in filtered.columns:
                values = filtered[column]
                mask |= _build_like_mask(values, query)
        filtered = filtered[mask]

    if format_filter and "format" in filtered.columns:
        filtered = filtered[filtered["format"].isin(format_filter)]

    ascending = sort_dir == "asc"
    if sort_by in filtered.columns:
        filtered = filtered.sort_values(by=sort_by, ascending=ascending, kind="stable")

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * page_size
    end = start + page_size

    return filtered.iloc[start:end].copy(), total_items, total_pages


def _path_scope_tag(abs_path: str, rawdata_dir: Path) -> str:
    path = Path(abs_path)
    try:
        relative = path.resolve().relative_to(rawdata_dir.resolve())
    except Exception:
        relative = path

    parts = relative.parts
    if len(parts) >= 2:
        return parts[0]
    if len(parts) == 1:
        return Path(parts[0]).stem or "root"
    return "root"


def build_convert_option_items(raw_df: pd.DataFrame, rawdata_dir: Path) -> list[dict]:
    if raw_df.empty:
        return []

    items: list[dict] = []
    for row in raw_df.itertuples(index=False):
        items.append(
            {
                "file_id": int(row.file_id),
                "name": str(row.name),
                "abs_path": str(row.abs_path),
                "format": str(row.format),
                "id": int(row.id),
            }
        )

    name_counts: dict[str, int] = {}
    for item in items:
        name_counts[item["name"]] = name_counts.get(item["name"], 0) + 1

    scope_index_map: dict[tuple[str, str], int] = {}
    for item in items:
        name = item["name"]
        if name_counts[name] == 1:
            item["label"] = f"{name} ({item['format']})"
            continue

        scope_tag = _path_scope_tag(item["abs_path"], rawdata_dir)
        key = (name, scope_tag)
        scope_index_map[key] = scope_index_map.get(key, 0) + 1
        idx = scope_index_map[key]
        item["label"] = f"{name} · {scope_tag}#{idx} ({item['format']})"

    return items
