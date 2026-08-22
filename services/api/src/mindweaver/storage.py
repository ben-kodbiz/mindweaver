"""Filesystem storage for original documents.

Documents are identified by stable IDs, never by filesystem path.
Originals are stored under ``settings.storage.originals_dir`` keyed by
``{document_id}.pdf``; derived data lives under
``settings.storage.derived_dir/{document_id}/``.
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path

from mindweaver.config import Settings


def original_path(settings: Settings, storage_key: str) -> Path:
    return settings.storage.originals_dir / storage_key


def delete_original(settings: Settings, storage_key: str) -> None:
    with contextlib.suppress(OSError):
        original_path(settings, storage_key).unlink(missing_ok=True)


def derived_dir(settings: Settings, document_id: str) -> Path:
    return settings.storage.derived_dir / document_id


def save_derived_json(settings: Settings, document_id: str, name: str, data: str) -> Path:
    directory = derived_dir(settings, document_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(data, encoding="utf-8")
    return path


def load_derived_json(settings: Settings, document_id: str, name: str) -> str | None:
    path = derived_dir(settings, document_id) / name
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def delete_derived(settings: Settings, document_id: str) -> None:
    shutil.rmtree(derived_dir(settings, document_id), ignore_errors=True)
