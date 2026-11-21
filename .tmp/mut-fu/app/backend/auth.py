"""Пароли, cookie-сессии и текущий пользователь."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .config import COOKIE_NAME, COOKIE_SECURE, SESSION_DAYS
from .deps import get_db
from .models import Integration, User, UserSession, WorkerToken, utcnow

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    return token


def delete_session(db: Session, token: str) -> None:
    db.query(UserSession).filter_by(token_hash=hash_token(token)).delete()
    db.commit()


def delete_user_sessions(db: Session, user_id: str) -> None:
    """Сброс пароля отзывает все учётные данные пользователя (M1-minor).

    Смена пароля — признак возможной компрометации: старые cookie-сессии,
    Bearer worker-токены и внешние токены (Яндекс.Диск) должны умереть.
    """
    db.query(UserSession).filter_by(user_id=user_id).delete()
    db.query(WorkerToken).filter_by(owner_id=user_id).delete()
    db.query(Integration).filter_by(owner_id=user_id).delete()
    db.commit()


def current_user(
    response: Response,
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    session = (
        db.query(UserSession)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    now = utcnow()
    if session is None or session.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session expired",
        )
    # Скользящее продление: раз в сутки до now + SESSION_DAYS.
    # Cookie живёт max_age от момента выдачи, поэтому её тоже перевыставляем.
    if session.expires_at < now + timedelta(days=SESSION_DAYS - 1):
        session.expires_at = now + timedelta(days=SESSION_DAYS)
        db.commit()
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=SESSION_DAYS * 86400,
            path="/",
        )
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found",
        )
    return user
