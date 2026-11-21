"""Настройки Яндекс.Диска (FR-15): OAuth одним кликом, ручной токен, шифр в БД."""
from __future__ import annotations

import json
import logging
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from .. import config, yadisk
from ..auth import current_user
from ..deps import get_db
from ..models import Integration, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

STATE_COOKIE = "yadisk_state"
STATE_TTL_SECONDS = 600
STATE_COOKIE_PATH = "/api/settings/yadisk"
# Серверного SPA-роута `/settings` нет: UI открывает вкладку сам по query.
CONNECTED_REDIRECT = "/?yadisk=connected"
ERROR_REDIRECT = "/?yadisk=error"


class YadiskSettingsOut(BaseModel):
    configured: bool
    masked: str | None = None


class YadiskSettingsIn(BaseModel):
    # Пустой/короткий токен или токен с пробелами — 422 на границе доверия.
    # Формат у Яндекса не проверяем (follow-up: реальный запрос к API).
    token: Annotated[
        str, StringConstraints(min_length=20, max_length=1024, pattern=r"^\S+$")
    ]


class AuthorizeOut(BaseModel):
    url: str


def _integration(db: Session, owner_id: str) -> Integration | None:
    return (
        db.query(Integration)
        .filter_by(owner_id=owner_id, kind=yadisk.KIND)
        .first()
    )


def _config_error(exc: yadisk.YadiskConfigError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
    )


def _require_oauth() -> None:
    if not yadisk.oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Yandex.Disk OAuth is not configured: "
                "set YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET"
            ),
        )


def _redirect(url: str) -> RedirectResponse:
    """Вернуть браузер в UI и погасить одноразовую state-cookie."""
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return response


@router.get("/yadisk", response_model=YadiskSettingsOut)
def get_yadisk_settings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> YadiskSettingsOut:
    integration = _integration(db, user.id)
    if integration is None or not integration.token_enc:
        return YadiskSettingsOut(configured=False, masked=None)
    try:
        raw = yadisk.decrypt_token(integration.token_enc)
    except yadisk.YadiskConfigError as exc:
        raise _config_error(exc) from exc
    return YadiskSettingsOut(
        configured=True, masked=yadisk.mask_token(yadisk.access_from_raw(raw))
    )


@router.put("/yadisk", response_model=YadiskSettingsOut)
def set_yadisk_settings(
    payload: YadiskSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> YadiskSettingsOut:
    # До шифрования/записи: отклонённый токен сразу даёт 422, недоступный
    # Яндекс — 503, и ничего не сохраняется. Ручной токен — fallback к OAuth.
    try:
        yadisk.validate_token(payload.token)
    except yadisk.YadiskUnauthorized as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except yadisk.YadiskError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        encrypted = yadisk.encrypt_token(yadisk.encode_manual_token(payload.token))
    except yadisk.YadiskConfigError as exc:
        raise _config_error(exc) from exc

    integration = _integration(db, user.id)
    if integration is None:
        integration = Integration(owner_id=user.id, kind=yadisk.KIND)
        db.add(integration)
    integration.token_enc = encrypted
    db.commit()
    return YadiskSettingsOut(
        configured=True, masked=yadisk.mask_token(payload.token)
    )


@router.delete("/yadisk", status_code=status.HTTP_204_NO_CONTENT)
def delete_yadisk_settings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    db.query(Integration).filter_by(
        owner_id=user.id, kind=yadisk.KIND
    ).delete()
    db.commit()


@router.get("/yadisk/authorize", response_model=AuthorizeOut)
def yadisk_authorize(
    response: Response,
    user: User = Depends(current_user),
) -> AuthorizeOut:
    """URL согласия Яндекса; state — в HttpOnly-cookie на 10 минут."""
    _require_oauth()
    state = secrets.token_urlsafe(32)
    response.set_cookie(
        key=STATE_COOKIE,
        value=state,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=STATE_TTL_SECONDS,
        path=STATE_COOKIE_PATH,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.YANDEX_CLIENT_ID,
            "redirect_uri": config.YANDEX_REDIRECT_URI,
            "state": state,
        }
    )
    return AuthorizeOut(url=f"{yadisk.OAUTH_AUTHORIZE_URL}?{query}")


@router.get("/yadisk/callback")
def yadisk_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    yadisk_state: str | None = Cookie(default=None, alias=STATE_COOKIE),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RedirectResponse:
    """Callback OAuth: сверить state, обменять code, сохранить токены, вернуть в UI.

    Ошибки тоже ведут в UI (`/?yadisk=error`): серверного роута `/settings`
    нет, а 400/502 в браузере пользователю ничего не объясняют.
    """
    _require_oauth()
    if error or not code or not state:
        return _redirect(ERROR_REDIRECT)
    if not yadisk_state or not secrets.compare_digest(state, yadisk_state):
        logger.warning("yadisk oauth state mismatch")
        return _redirect(ERROR_REDIRECT)
    try:
        tokens = yadisk.exchange_code(code)
    except yadisk.YadiskOAuthError as exc:  # отказ Яндекса и сеть
        logger.warning("yadisk oauth exchange failed: %s", exc)
        return _redirect(ERROR_REDIRECT)
    try:
        encrypted = yadisk.encrypt_token(json.dumps(tokens))
    except yadisk.YadiskConfigError as exc:
        raise _config_error(exc) from exc

    integration = _integration(db, user.id)
    if integration is None:
        integration = Integration(owner_id=user.id, kind=yadisk.KIND)
        db.add(integration)
    integration.token_enc = encrypted
    db.commit()
    return _redirect(CONNECTED_REDIRECT)
