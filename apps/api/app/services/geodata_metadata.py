from __future__ import annotations

from typing import Any


def serialize_schema(gdf: Any) -> dict[str, str]:
    schema: dict[str, str] = {}
    for col, dtype in gdf.dtypes.items():
        if col == gdf.geometry.name:
            continue
        schema[str(col)] = str(dtype)
    return schema


def bbox_dict(gdf: Any) -> dict[str, float] | None:
    if gdf.empty:
        return None
    min_x, min_y, max_x, max_y = gdf.total_bounds
    return {"min_x": float(min_x), "min_y": float(min_y), "max_x": float(max_x), "max_y": float(max_y)}


def geom_type(gdf: Any) -> str | None:
    if gdf.empty:
        return None
    geom_types = sorted({str(value) for value in gdf.geom_type.dropna().unique()})
    return ",".join(geom_types) if geom_types else None
