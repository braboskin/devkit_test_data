"""Яндекс.Диск (FR-15, A11): токен шифром, выгрузка и удаление оригиналов.

Токен хранится только шифром (`integrations.token_enc`), ключ — env
`ATLAS_FERNET_KEY` (base64 32 bytes). В логи и ответы API токен не попадает:
только маска `***<последние 4>`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .models import Document, Integration, User

logger = logging.getLogger(__name__)

KIND = "yadisk"
API_URL = "https://cloud-api.yandex.net/v1/disk/resources"
REMOTE_ROOT = "/atlas"
TIMEOUT_SECONDS = 30.0


class YadiskError(Exception):
    """Сбой REST Яндекс.Диска: сеть, статус ответа или его формат."""


class YadiskConfigError(Exception):
    """Нет/неверный `ATLAS_FERNET_KEY`: токен невозможно прочитать."""


# ---------- шифрование токена ----------


def _fernet() -> Fernet:
    key = os.environ.get("ATLAS_FERNET_KEY", "").strip()
    if not key:
        raise YadiskConfigError(
            "ATLAS_FERNET_KEY is not set: cannot store the Yandex.Disk token"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise YadiskConfigError(
            "ATLAS_FERNET_KEY is invalid: expected base64 32 bytes"
        ) from exc


def encrypt_token(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_token(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeEncodeError) as exc:
        raise YadiskConfigError(
            "stored Yandex.Disk token cannot be decrypted: check ATLAS_FERNET_KEY"
        ) from exc


def mask_token(raw: str) -> str:
    return "***" + raw[-4:]


# ---------- REST Яндекс.Диска ----------


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"OAuth {token}"}


def _check_status(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        raise YadiskError(f"{action} failed with HTTP {response.status_code}")


def _upload_href(token: str, remote_path: str) -> str:
    """`resources/upload` → подписанная ссылка для PUT."""
    try:
        response = httpx.get(
            f"{API_URL}/upload",
            params={"path": remote_path, "overwrite": "true"},
            headers=_headers(token),
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise YadiskError("upload link request failed") from exc
    _check_status(response, "upload link request")
    try:
        href = response.json().get("href")
    except ValueError as exc:
        raise YadiskError("upload link response is not JSON") from exc
    if not href:
        raise YadiskError("upload link response has no href")
    return href


def upload_file(token: str, remote_path: str, local_path: Path) -> None:
    """Выгрузить оригинал: GET ссылки `resources/upload`, затем PUT тела файла."""
    href = _upload_href(token, remote_path)
    try:
        with Path(local_path).open("rb") as stream:
            # `href` — подписанная ссылка на хранилище: OAuth туда не отправляем.
            response = httpx.put(href, content=stream, timeout=TIMEOUT_SECONDS)
    except OSError as exc:
        raise YadiskError("original cannot be read") from exc
    except httpx.HTTPError as exc:
        raise YadiskError("upload failed") from exc
    _check_status(response, "upload")


def delete_file(token: str, remote_path: str) -> None:
    try:
        response = httpx.delete(
            API_URL,
            params={"path": remote_path, "permanently": "true"},
            headers=_headers(token),
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise YadiskError("remote delete failed") from exc
    if response.status_code != 404:  # 404 — файла уже нет, цель достигнута.
        _check_status(response, "remote delete")


# ---------- операции над документами ----------


def _token_for(db: Session, owner_id: str) -> str | None:
    integration = (
        db.query(Integration).filter_by(owner_id=owner_id, kind=KIND).first()
    )
    if integration is None or not integration.token_enc:
        return None
    try:
        return decrypt_token(integration.token_enc)
    except YadiskConfigError as exc:
        logger.warning("yadisk token is unavailable: %s", exc)
        return None


def _remote_path(owner_id: str, document_id: int, suffix: str) -> str:
    return f"{REMOTE_ROOT}/{owner_id}/{document_id}{suffix.lower()}"


def _api_path(storage_ref: str) -> str:
    return storage_ref[5:] if storage_ref.startswith("disk:") else storage_ref


def store_original(
    db: Session, user: User, document: Document, local_path: Path
) -> bool:
    """Выгрузить оригинал владельца в `/atlas/<user>/<document>.<ext>`.

    True — документ переведён на `storage='yandex'`. Без токена или при
    ошибке API — False: локальная копия остаётся, причина — в `document.error`
    (только текст ошибки, без токена).
    """
    token = _token_for(db, user.id)
    if token is None or document.id is None:
        return False
    remote = _remote_path(user.id, document.id, Path(local_path).suffix)
    try:
        upload_file(token, remote, local_path)
    except YadiskError as exc:
        logger.warning("yadisk upload failed for document %s: %s", document.id, exc)
        document.error = "yandex disk upload failed"
        db.commit()
        return False
    document.storage = "yandex"
    document.storage_ref = f"disk:{remote}"
    db.commit()
    return True


def delete_original(db: Session, user: User, document: Document) -> bool:
    """Удалить облачный оригинал; ошибка не должна валить удаление документа."""
    if document.storage != "yandex" or not document.storage_ref:
        return False
    token = _token_for(db, user.id)
    if token is None:
        logger.warning(
            "yadisk token is unavailable: remote original of document %s kept",
            document.id,
        )
        return False
    try:
        delete_file(token, _api_path(document.storage_ref))
    except YadiskError as exc:
        logger.warning("yadisk delete failed for document %s: %s", document.id, exc)
        return False
    return True
