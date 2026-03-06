from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from app.services.conversion_service import _read_csv


def test_read_csv_supports_cp949_encoding() -> None:
    tmp_root = Path("tmp") / "test_conversion_service" / f"cp949-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        csv_path = tmp_root / "sample_cp949.csv"
        csv_path.write_bytes("lat,lon,name\n37.5,127.0,테스트\n".encode("cp949"))

        gdf = _read_csv(
            csv_path,
            lat_col="lat",
            lon_col="lon",
            input_crs="EPSG:4326",
        )

        assert len(gdf) == 1
        assert str(gdf.iloc[0]["name"]) == "테스트"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
