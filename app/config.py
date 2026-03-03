from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    project_root: Path
    rawdata_dir: Path
    data_dir: Path
    data_upload_dir: Path
    data_wfs_dir: Path
    database_url: str
    vworld_api_key: str | None
    app_encryption_key: str | None
    wfs_catalog_path: Path



def get_settings() -> Settings:
    project_root = Path(os.getenv("PROJECT_ROOT", Path.cwd())).resolve()
    rawdata_dir = project_root / "rawdata"
    data_dir = project_root / "data"
    data_upload_dir = data_dir / "upload"
    data_wfs_dir = data_dir / "wfs"
    wfs_catalog_path = Path(os.getenv("WFS_CATALOG_PATH", project_root / "wfs" / "브이월드_WFS_컬럼정보.xlsx")).resolve()
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
    )
    return Settings(
        project_root=project_root,
        rawdata_dir=rawdata_dir,
        data_dir=data_dir,
        data_upload_dir=data_upload_dir,
        data_wfs_dir=data_wfs_dir,
        database_url=database_url,
        vworld_api_key=os.getenv("VWORLD_API_KEY"),
        app_encryption_key=os.getenv("APP_ENCRYPTION_KEY"),
        wfs_catalog_path=wfs_catalog_path,
    )
