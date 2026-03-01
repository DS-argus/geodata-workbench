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
    database_url: str



def get_settings() -> Settings:
    project_root = Path(os.getenv("PROJECT_ROOT", Path.cwd())).resolve()
    rawdata_dir = project_root / "rawdata"
    data_dir = project_root / "data"
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/geodata",
    )
    return Settings(
        project_root=project_root,
        rawdata_dir=rawdata_dir,
        data_dir=data_dir,
        database_url=database_url,
    )
