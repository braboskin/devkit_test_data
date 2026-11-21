"""Яндекс.Диск (FR-15, A11): токен шифром, выгрузка и удаление оригиналов.

Токен хранится только шифром (`integrations.token_enc`), ключ — env
`ATLAS_FERNET_KEY` (base64 32 bytes). В логи и ответы API токен не попадает:
только маска `***<последние 4>`.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from . import config, storage
from .models import Document, Integration, User, utcnow

logger = logging.getLogger(__name__)

KIND = "yadisk"
DISK_URL = "https://cloud-api.yandex.net/v1/disk"
API_URL = "https://cloud-api.yandex.net/v1/disk/resources"
REMOTE_ROOT = "/atlas"
TIMEOUT_SECONDS = 30.0
OAUTH_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
OAUTH_TOKEN_URL = "https://oauth.yandex.ru/token"
# Access обновляем заранее: иначе истёкший токен проскочит в REST-вызов.
REFRESH_SKEW_SECONDS = 60


class YadiskError(Exception):
    """Сбой REST Яндекс.Диска: сеть, статус ответа или его формат."""


class YadiskUnauthorized(YadiskError):
    """Яндекс отклонил токен (401/403): истёк, отозван или нет scope."""


class YadiskConfigError(Exception):
    """Нет/неверный `ATLAS_FERNET_KEY`: токен невозможно прочитать."""


class YadiskOAuthError(YadiskError):
    """Обмен code/refresh не удался: сеть или неожиданный ответ Яндекса."""


class YadiskOAuthRejected(YadiskOAuthError):
    """Яндекс отклонил обмен code/refresh (HTTP 4xx): плохой/протухший код."""


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
    """Безопасная маска: короткий токен не показываем даже частично."""
    if len(raw) < 12:
        return "***"
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


def ensure_folder(token: str, path: str) -> None:
    """Создать папку (идемпотентно); 409 — папка уже существует.

    Родительская папка должна быть создана раньше: Яндекс не создаёт цепочку.
    """
    try:
        response = httpx.put(
            API_URL,
            params={"path": path},
            headers=_headers(token),
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise YadiskError("folder creation failed") from exc
    if response.status_code in (201, 409):
        return
    if response.status_code in (401, 403):
        raise YadiskUnauthorized("Yandex rejected the token")
    raise YadiskError(f"folder creation failed with HTTP {response.status_code}")


def validate_token(token: str) -> None:
    """Проверить токен через `GET /v1/disk`; иначе — исключение."""
    try:
        response = httpx.get(
            DISK_URL, headers=_headers(token), timeout=TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        raise YadiskError("cannot verify token with Yandex") from exc
    if response.status_code in (401, 403):
        raise YadiskUnauthorized("Yandex rejected the token")
    if response.status_code != 200:
        raise YadiskError("cannot verify token with Yandex")


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


def _download_href(token: str, remote_path: str) -> str:
    """`resources/download` → подписанная ссылка на чтение."""
    try:
        response = httpx.get(
            f"{API_URL}/download",
            params={"path": remote_path},
            headers=_headers(token),
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise YadiskError("download link request failed") from exc
    _check_status(response, "download link request")
    try:
        href = response.json().get("href")
    except ValueError as exc:
        raise YadiskError("download link response is not JSON") from exc
    if not href:
        raise YadiskError("download link response has no href")
    return href


def download_file(token: str, remote_path: str, dest: Path) -> None:
    """Скачать облачный оригинал: GET ссылки, затем GET тела в файл.

    OAuth уходит только к API: `href` — подписанная ссылка на хранилище.
    Потолок размера — `MAX_UPLOAD_BYTES` (документ не мог быть больше при
    загрузке); недокачанный файл при сбое удаляем.
    """
    href = _download_href(token, remote_path)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", href, timeout=TIMEOUT_SECONDS) as response:
            _check_status(response, "download")
            written = 0
            with dest.open("wb") as out:
                for chunk in response.iter_bytes():
                    written += len(chunk)
                    if written > config.MAX_UPLOAD_BYTES:
                        raise YadiskError("downloaded original is too large")
                    out.write(chunk)
    except YadiskError:
        dest.unlink(missing_ok=True)
        raise
    except httpx.HTTPError as exc:
        dest.unlink(missing_ok=True)
        raise YadiskError("download failed") from exc
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise YadiskError("original cannot be written") from exc


# ---------- OAuth и токены ----------


def oauth_configured() -> bool:
    """OAuth доступен только при заданных env (иначе эндпоинты отвечают 503)."""
    return bool(config.YANDEX_CLIENT_ID and config.YANDEX_CLIENT_SECRET)


def _json_tokens(raw: str) -> dict | None:
    """JSON-токены OAuth; старый формат (один raw-токен) → None."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def encode_manual_token(access_token: str) -> str:
    """Ручной токен — тот же JSON без refresh (fallback к OAuth)."""
    return json.dumps(
        {"access_token": access_token, "refresh_token": "", "expires_at": None}
    )


def access_from_raw(raw: str) -> str:
    """Access-токен из сохранённого значения: JSON (OAuth/ручной) или старый raw."""
    data = _json_tokens(raw)
    return raw if data is None else str(data.get("access_token") or "")


def _post_token(form: dict[str, str]) -> dict:
    """POST на token-эндпоинт Яндекса; тело в лог не попадает (там секреты)."""
    try:
        response = httpx.post(OAUTH_TOKEN_URL, data=form, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise YadiskOAuthError("token request failed") from exc
    if response.status_code >= 400:
        raise YadiskOAuthRejected(
            f"token request rejected with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise YadiskOAuthError("token response is not JSON") from exc
    if not str(payload.get("access_token") or ""):
        raise YadiskOAuthError("token response has no access_token")
    return payload


def _tokens_from_payload(payload: dict, previous_refresh: str = "") -> dict:
    try:
        seconds = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        seconds = 0
    expires_at = utcnow() + timedelta(seconds=max(seconds, 0))
    return {
        "access_token": str(payload["access_token"]),
        "refresh_token": str(
            payload.get("refresh_token") or previous_refresh or ""
        ),
        "expires_at": expires_at.isoformat(),
    }


def exchange_code(code: str) -> dict:
    """Обменять authorization code на токены (шифрует и сохраняет вызывающий)."""
    return _tokens_from_payload(
        _post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.YANDEX_CLIENT_ID,
                "client_secret": config.YANDEX_CLIENT_SECRET,
                "redirect_uri": config.YANDEX_REDIRECT_URI,
            }
        )
    )


def refresh_tokens(
    db: Session, integration: Integration, data: dict
) -> str | None:
    """Обновить access по refresh; None — не вышло, прежний токен остаётся."""
    refresh = str((data or {}).get("refresh_token") or "").strip()
    if not refresh:
        return None
    try:
        payload = _post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": config.YANDEX_CLIENT_ID,
                "client_secret": config.YANDEX_CLIENT_SECRET,
            }
        )
    except YadiskError as exc:
        logger.warning("yadisk token refresh failed: %s", exc)
        return None
    tokens = _tokens_from_payload(payload, previous_refresh=refresh)
    try:
        integration.token_enc = encrypt_token(json.dumps(tokens))
    except YadiskConfigError as exc:
        logger.warning("yadisk refreshed token is not saved: %s", exc)
        return None
    db.commit()
    return tokens["access_token"]


def _expires_soon(value: object) -> bool:
    if not value:
        return False
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment <= utcnow() + timedelta(seconds=REFRESH_SKEW_SECONDS)


def _token_for(db: Session, owner_id: str) -> str | None:
    integration = (
        db.query(Integration).filter_by(owner_id=owner_id, kind=KIND).first()
    )
    if integration is None or not integration.token_enc:
        return None
    try:
        raw = decrypt_token(integration.token_enc)
    except YadiskConfigError as exc:
        logger.warning("yadisk token is unavailable: %s", exc)
        return None
    data = _json_tokens(raw)
    if data is None:
        return raw
    access = str(data.get("access_token") or "").strip()
    if not access:
        return None
    if _expires_soon(data.get("expires_at")):
        refreshed = refresh_tokens(db, integration, data)
        if refreshed is not None:
            return refreshed
    return access


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
        ensure_folder(token, REMOTE_ROOT)
        ensure_folder(token, f"{REMOTE_ROOT}/{user.id}")
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


def ensure_local_original(
    db: Session, user: User, document: Document
) -> Path | None:
    """Локальная копия оригинала; для `yandex` при её отсутствии — скачать.

    Скачанное кладём в `ATLAS_STORAGE_DIR/<owner>/<id><ext>` — тот же путь,
    что у локальных оригиналов, поэтому `storage.local_original` найдёт копию.
    """
    local = storage.local_original(
        document.owner_id, document.id, document.storage, document.storage_ref
    )
    if local is not None:
        return local
    if (
        document.storage != "yandex"
        or not document.storage_ref
        or document.id is None
    ):
        return None
    token = _token_for(db, user.id)
    if token is None:
        return None
    remote = _api_path(document.storage_ref)
    dest = storage.owner_dir(document.owner_id) / (
        f"{document.id}{Path(remote).suffix.lower()}"
    )
    try:
        download_file(token, remote, dest)
    except YadiskError as exc:
        logger.warning("yadisk download failed for document %s: %s", document.id, exc)
        return None
    return dest
