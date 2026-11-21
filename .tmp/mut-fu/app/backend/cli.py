"""CLI управления пользователями Atlas Chat.

Схему создают миграции: перед первым запуском `alembic upgrade head`.
"""
from __future__ import annotations

import argparse
import getpass
import uuid

from .auth import delete_user_sessions, hash_password
from .config import DB_URL
from .db import make_engine, make_session_factory
from .models import User


def prompt_password() -> str:
    password = getpass.getpass("Пароль: ")
    if len(password) < 8:
        raise SystemExit("пароль должен быть не короче 8 символов")
    confirm = getpass.getpass("Повторите пароль: ")
    if password != confirm:
        raise SystemExit("пароли не совпадают")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas Chat: пользователи")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user")
    create.add_argument("--username", required=True)
    create.add_argument(
        "--password",
        default=None,
        help="для автоматизации; без флага пароль запрашивается",
    )

    sub.add_parser("list-users")

    reset = sub.add_parser("reset-password")
    reset.add_argument("--username", required=True)

    args = parser.parse_args(argv)

    engine = make_engine(DB_URL)
    Session = make_session_factory(engine)

    with Session() as db:
        if args.command == "create-user":
            if db.query(User).filter_by(username=args.username).first():
                print(f"пользователь уже существует: {args.username}")
                return 1
            password = args.password or prompt_password()
            if len(password) < 8:
                print("пароль должен быть не короче 8 символов")
                return 1
            user = User(
                id=str(uuid.uuid4()),
                username=args.username,
                password_hash=hash_password(password),
            )
            db.add(user)
            db.commit()
            print(f"создан: {user.username}")
            return 0

        if args.command == "list-users":
            users = db.query(User).order_by(User.username).all()
            for user in users:
                print(f"{user.username}\t{user.created_at:%Y-%m-%d}")
            return 0

        if args.command == "reset-password":
            user = db.query(User).filter_by(username=args.username).first()
            if user is None:
                print(f"пользователь не найден: {args.username}")
                return 1
            user.password_hash = hash_password(prompt_password())
            db.commit()
            # Смена пароля отзывает все учётные данные пользователя.
            delete_user_sessions(db, user.id)
            print(f"пароль обновлён: {user.username}")
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
