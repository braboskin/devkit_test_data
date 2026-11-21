"""Локальное хранилище оригиналов: вне web-root, каталог на владельца.

`documents.storage_ref` — относительный путь `<owner_id>/<document_id>.<ext>`
(резолвится через `resolve`), чтобы каталог хранилища можно было переносить.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import BinaryIO

from . import config

CHUNK_BYTES = 1024 * 1024


class StorageLimitExceeded(Exception):
    """Файл больше `ATLAS_MAX_UPLOAD_MB`: чтение прекращается сразу."""


def root() -> Path:
    path = Path(config.STORAGE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def owner_dir(owner_id: str) -> Path:
    path = root() / owner_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve(storage_ref: str) -> Path:
    """Путь к оригиналу по `storage_ref`; принимать только свои ref из БД."""
    return root() / storage_ref


def local_original(
    owner_id: str, document_id: int, storage: str, storage_ref: str | None
) -> Path | None:
    """Локальная копия оригинала, если она есть (в том числе при `yandex`).

    При `storage='yandex'` в `storage_ref` лежит облачная ссылка `disk:/...`,
    поэтому копию ищем в каталоге владельца по имени `<document_id>.<ext>`.
    """
    if storage == "local" and storage_ref:
        path = resolve(storage_ref)
        if path.is_file():
            return path
    directory = Path(config.STORAGE_DIR) / owner_id
    if not directory.is_dir():
        return None
    for candidate in sorted(directory.glob(f"{document_id}.*")):
        if candidate.is_file():
            return candidate
    return None


def save_stream(
    stream: BinaryIO, owner_id: str, max_bytes: int
) -> tuple[Path, int, str]:
    """Стриминг во временный файл: (путь, размер, sha256).

    Размер проверяется до записи очередного блока, поэтому в память файл
    целиком не попадает, а при превышении лимита временный файл удаляется.
    """
    tmp = owner_dir(owner_id) / f"tmp-{uuid.uuid4().hex}"
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            while True:
                chunk = stream.read(CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise StorageLimitExceeded
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, size, digest.hexdigest()


def finalize(tmp: Path, owner_id: str, document_id: int, ext: str) -> str:
    """Перенести временный файл в `<owner_id>/<document_id><ext>`; вернуть ref."""
    dest = owner_dir(owner_id) / f"{document_id}{ext}"
    tmp.replace(dest)
    return f"{owner_id}/{dest.name}"


def delete(storage_ref: str | None) -> None:
    """Удалить локальный оригинал (ошибка удаления не должна ронять запрос)."""
    if storage_ref:
        resolve(storage_ref).unlink(missing_ok=True)
