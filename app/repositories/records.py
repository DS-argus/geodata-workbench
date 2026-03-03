from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSecretRecord, DatasetRecord, FileRecord, JobRecord


def create_file(
    session: Session,
    *,
    category: str,
    path: str,
    name: str,
    format: str,
    size_bytes: int,
    crs: str | None = None,
) -> FileRecord:
    record = FileRecord(
        category=category,
        path=path,
        name=name,
        format=format,
        size_bytes=size_bytes,
        crs=crs,
    )
    session.add(record)
    session.flush()
    return record


def list_files(session: Session, category: str | None = None) -> list[FileRecord]:
    stmt = select(FileRecord).order_by(FileRecord.created_at.desc())
    if category:
        stmt = stmt.where(FileRecord.category == category)
    return list(session.scalars(stmt).all())


def get_file(session: Session, file_id: int) -> FileRecord | None:
    return session.get(FileRecord, file_id)


def create_job(
    session: Session,
    *,
    job_type: str,
    status: str,
    input_file_id: int | None,
    params_json: dict | None = None,
) -> JobRecord:
    record = JobRecord(
        job_type=job_type,
        status=status,
        input_file_id=input_file_id,
        params_json=params_json,
        progress_percent=0,
        progress_message=None,
    )
    session.add(record)
    session.flush()
    return record


def update_job(
    session: Session,
    job: JobRecord,
    *,
    status: str,
    output_file_id: int | None = None,
    error_message: str | None = None,
    progress_percent: int | None = None,
    progress_message: str | None = None,
) -> JobRecord:
    job.status = status
    job.output_file_id = output_file_id
    job.error_message = error_message
    if progress_percent is not None:
        job.progress_percent = max(0, min(100, int(progress_percent)))
    elif status == "succeeded":
        job.progress_percent = 100
    if progress_message is not None:
        job.progress_message = progress_message
    job.finished_at = datetime.now(tz=timezone.utc)
    session.add(job)
    session.flush()
    return job


def set_job_progress(
    session: Session,
    job: JobRecord,
    *,
    progress_percent: int,
    progress_message: str | None = None,
) -> JobRecord:
    job.progress_percent = max(0, min(100, int(progress_percent)))
    if progress_message is not None:
        job.progress_message = progress_message
    session.add(job)
    session.flush()
    return job


def create_dataset(
    session: Session,
    *,
    file_id: int,
    geom_type: str | None,
    feature_count: int,
    bbox: dict | None,
    properties_schema_json: dict | None,
) -> DatasetRecord:
    record = DatasetRecord(
        file_id=file_id,
        geom_type=geom_type,
        feature_count=feature_count,
        bbox=bbox,
        properties_schema_json=properties_schema_json,
    )
    session.add(record)
    session.flush()
    return record


def list_jobs(session: Session) -> list[JobRecord]:
    stmt = select(JobRecord).order_by(JobRecord.created_at.desc())
    return list(session.scalars(stmt).all())


def get_job(session: Session, job_id: int) -> JobRecord | None:
    return session.get(JobRecord, job_id)


def delete_file_and_related(session: Session, file_id: int) -> str | None:
    file_record = session.get(FileRecord, file_id)
    if file_record is None:
        return None

    session.query(DatasetRecord).filter(DatasetRecord.file_id == file_id).delete(
        synchronize_session=False
    )
    session.query(JobRecord).filter(
        (JobRecord.input_file_id == file_id) | (JobRecord.output_file_id == file_id)
    ).delete(synchronize_session=False)
    session.delete(file_record)
    session.flush()
    return file_record.path


def dataset_feature_count_map(session: Session) -> dict[int, int]:
    stmt = select(DatasetRecord.file_id, DatasetRecord.feature_count)
    rows = session.execute(stmt).all()
    return {int(file_id): int(feature_count) for file_id, feature_count in rows}


def get_secret(session: Session, secret_key: str) -> AppSecretRecord | None:
    stmt = select(AppSecretRecord).where(AppSecretRecord.secret_key == secret_key)
    return session.scalars(stmt).first()


def upsert_secret(session: Session, secret_key: str, encrypted_value: str) -> AppSecretRecord:
    record = get_secret(session, secret_key)
    if record is None:
        record = AppSecretRecord(secret_key=secret_key, encrypted_value=encrypted_value)
    else:
        record.encrypted_value = encrypted_value
    session.add(record)
    session.flush()
    return record
