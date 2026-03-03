from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories import get_secret, upsert_secret


VWORLD_SECRET_KEY = "vworld_api_key"


def _runtime_key_path(project_root: Path) -> Path:
    return project_root / ".runtime" / "fernet.key"


def _derive_fallback_key(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def get_or_create_encryption_key() -> str:
    settings = get_settings()
    if settings.app_encryption_key:
        return settings.app_encryption_key.strip()

    key_path = _runtime_key_path(settings.project_root)
    try:
        if key_path.exists():
            return key_path.read_text(encoding="utf-8").strip()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key().decode("utf-8")
        key_path.write_text(key, encoding="utf-8")
        return key
    except Exception:
        return _derive_fallback_key(settings.database_url)


def _fernet() -> Fernet:
    key = get_or_create_encryption_key().encode("utf-8")
    return Fernet(key)


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def set_secret_value(session: Session, *, key: str, value: str) -> None:
    encrypted = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    upsert_secret(session, key, encrypted)


def get_secret_value(session: Session, key: str) -> str | None:
    record = get_secret(session, key)
    if record is None:
        return None
    try:
        decrypted = _fernet().decrypt(record.encrypted_value.encode("utf-8"))
    except Exception:
        return None
    return decrypted.decode("utf-8")
