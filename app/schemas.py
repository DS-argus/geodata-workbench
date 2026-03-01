from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FileDTO(BaseModel):
    id: int
    category: str
    path: str
    name: str
    format: str
    size_bytes: int
    crs: str | None
    created_at: datetime


class JobDTO(BaseModel):
    id: int
    job_type: str
    status: str
    input_file_id: int | None
    output_file_id: int | None
    params_json: dict | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
