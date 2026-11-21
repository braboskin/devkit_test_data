"""FastAPI-приложение Atlas Chat."""
from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import (
    current_user,
    delete_session,
    new_session,
    verify_password,
)
from .config import (
    COOKIE_NAME,
    COOKIE_SECURE,
    CORS_ORIGINS,
    DB_URL,
    ROOT,
    SESSION_DAYS,
)
from .db import make_engine, make_session_factory
from .deps import get_db
from .models import User
from . import routers as routers_pkg
from .schemas import LoginRequest, UserOut


def create_app(database_url: str | None = None) -> FastAPI:
    # Engine ленивый: без БД приложение создаётся, подключение — по запросу.
    engine = make_engine(database_url or DB_URL)

    app = FastAPI(title="Atlas Chat", version="0.1.0")
    app.state.engine = engine
    app.state.SessionLocal = make_session_factory(engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/auth/login", response_model=UserOut)
    def login(
        payload: LoginRequest,
        response: Response,
        db: Session = Depends(get_db),
    ) -> User:
        user = db.query(User).filter_by(username=payload.username).first()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
            )
        token = new_session(db, user)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=SESSION_DAYS * 86400,
            path="/",
        )
        return user

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        db: Session = Depends(get_db),
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    ) -> dict:
        if token:
            delete_session(db, token)
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/api/me", response_model=UserOut)
    def me(user: User = Depends(current_user)) -> User:
        return user

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # Роутеры подключаются автоматически: любой routers/<name>.py с `router`.
    for info in iter_modules(routers_pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = import_module(f"{__package__}.routers.{info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)

    dist = ROOT / "viewer" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="viewer")
    else:

        @app.get("/")
        def root() -> dict:
            return {"service": "atlas-chat", "status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="127.0.0.1", port=8000)
