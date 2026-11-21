"""FR-1: вход, сессии, скользящее продление. Два равноправных аккаунта."""
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.backend import cli
from app.backend.auth import hash_password
from app.backend.config import ROOT
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import (
    Integration,
    User,
    UserSession,
    WorkerToken,
    utcnow,
)

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{(Path(self.tmp.name) / 'test.db').as_posix()}"
        self.app = create_app(self.url)
        self.engine = self.app.state.engine
        Base.metadata.create_all(self.engine)
        with self.app.state.SessionLocal() as db:
            db.add_all(
                [
                    User(
                        username=ALICE["username"],
                        password_hash=hash_password(ALICE["password"]),
                    ),
                    User(
                        username=BOB["username"],
                        password_hash=hash_password(BOB["password"]),
                    ),
                ]
            )
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _expiry(self) -> object:
        with self.app.state.SessionLocal() as db:
            return db.query(UserSession).one().expires_at

    def test_health(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")

    def test_login_me_logout(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            self.assertIn("atlas_session", client.cookies)

            me = client.get("/api/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["username"], "alice")
            self.assertNotIn("role", me.json())

            logout = client.post("/api/auth/logout")
            self.assertEqual(logout.status_code, 200)
            self.assertEqual(client.get("/api/me").status_code, 401)

    def test_two_accounts_are_equal(self) -> None:
        with TestClient(self.app) as alice_client, TestClient(self.app) as bob_client:
            self._login(alice_client, ALICE)
            self._login(bob_client, BOB)

            alice = alice_client.get("/api/me").json()
            bob = bob_client.get("/api/me").json()
            self.assertEqual(alice["username"], "alice")
            self.assertEqual(bob["username"], "bob")
            self.assertNotEqual(alice["id"], bob["id"])
            self.assertNotIn("role", alice)
            self.assertNotIn("role", bob)

    def test_wrong_password(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong"},
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "invalid credentials")

    def test_me_requires_session(self) -> None:
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/me").status_code, 401)

    def test_expired_session_is_rejected(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            with self.app.state.SessionLocal() as db:
                db.query(UserSession).one().expires_at = utcnow() - timedelta(
                    seconds=1
                )
                db.commit()
            response = client.get("/api/me")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("set-cookie", response.headers)

    def test_session_slides_forward(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            with self.app.state.SessionLocal() as db:
                db.query(UserSession).one().expires_at = utcnow() + timedelta(days=28)
                db.commit()

            response = client.get("/api/me")
            self.assertEqual(response.status_code, 200)
            set_cookie = response.headers.get("set-cookie", "")
            self.assertIn("atlas_session=", set_cookie)
            self.assertIn("Max-Age=2592000", set_cookie)
            self.assertIn("HttpOnly", set_cookie)
            self.assertIn("SameSite=lax", set_cookie)
            self.assertGreater(self._expiry(), utcnow() + timedelta(days=29))

            # «Не чаще раза в сутки»: следующий запрос cookie не перевыставляет.
            expires_after_first = self._expiry()
            again = client.get("/api/me")
            self.assertEqual(again.status_code, 200)
            self.assertNotIn("set-cookie", again.headers)
            self.assertEqual(self._expiry(), expires_after_first)

    def test_reset_password_invalidates_sessions(self) -> None:
        with TestClient(self.app) as first, TestClient(self.app) as second:
            self._login(first, ALICE)
            self._login(second, ALICE)
            with (
                mock.patch.object(cli, "make_engine", return_value=self.engine),
                mock.patch.object(
                    cli, "prompt_password", return_value="new-pass-123"
                ),
            ):
                self.assertEqual(
                    cli.main(["reset-password", "--username", "alice"]), 0
                )
            # Обе выданные сессии инвалидированы.
            self.assertEqual(first.get("/api/me").status_code, 401)
            self.assertEqual(second.get("/api/me").status_code, 401)
            with self.app.state.SessionLocal() as db:
                self.assertEqual(db.query(UserSession).count(), 0)

            # Старый пароль не подходит, новый — да.
            self.assertEqual(
                first.post("/api/auth/login", json=ALICE).status_code, 401
            )
            self._login(first, {"username": "alice", "password": "new-pass-123"})
            self.assertEqual(first.get("/api/me").status_code, 200)

    def test_reset_password_revokes_worker_token_and_integrations(self) -> None:
        """Смена пароля убивает Bearer worker-токен и внешние токены, не чужие."""
        with TestClient(self.app) as client, TestClient(self.app) as bob_client:
            self._login(client, ALICE)
            alice_id = client.get("/api/me").json()["id"]
            alice_token = client.post("/api/settings/worker-token").json()["token"]
            alice_headers = {"Authorization": f"Bearer {alice_token}"}
            self.assertEqual(
                client.post("/api/worker/claim", headers=alice_headers).status_code,
                204,
            )
            self._login(bob_client, BOB)
            bob_token = bob_client.post("/api/settings/worker-token").json()["token"]
            bob_headers = {"Authorization": f"Bearer {bob_token}"}
            with self.app.state.SessionLocal() as db:
                bob_id = db.query(User).filter_by(username=BOB["username"]).one().id
                db.add(
                    Integration(owner_id=alice_id, kind="yadisk", token_enc="cipher")
                )
                db.add(
                    Integration(owner_id=bob_id, kind="yadisk", token_enc="cipher")
                )
                db.commit()

            with (
                mock.patch.object(cli, "make_engine", return_value=self.engine),
                mock.patch.object(
                    cli, "prompt_password", return_value="new-pass-123"
                ),
            ):
                self.assertEqual(
                    cli.main(["reset-password", "--username", "alice"]), 0
                )

            # Cookie-сессия и Bearer worker-токен отозваны.
            self.assertEqual(client.get("/api/me").status_code, 401)
            self.assertEqual(
                client.post("/api/worker/claim", headers=alice_headers).status_code,
                401,
            )
            with self.app.state.SessionLocal() as db:
                self.assertEqual(
                    db.query(WorkerToken).filter_by(owner_id=alice_id).count(), 0
                )
                self.assertEqual(
                    db.query(Integration).filter_by(owner_id=alice_id).count(), 0
                )
            # Учётные данные второго владельца не затронуты.
            self.assertEqual(
                bob_client.post("/api/worker/claim", headers=bob_headers).status_code,
                204,
            )
            with self.app.state.SessionLocal() as db:
                self.assertEqual(
                    db.query(WorkerToken).filter_by(owner_id=bob_id).count(), 1
                )
                self.assertEqual(
                    db.query(Integration).filter_by(owner_id=bob_id).count(), 1
                )

    def test_root_json_without_viewer_build(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        if (ROOT / "viewer" / "dist" / "index.html").is_file():
            self.assertIn("text/html", response.headers["content-type"])
        else:
            self.assertEqual(
                response.json(),
                {"service": "atlas-chat", "status": "ok"},
            )

    def test_app_starts_without_database(self) -> None:
        app = create_app("postgresql+psycopg://nobody@127.0.0.1:1/none")
        try:
            with TestClient(app) as client:
                self.assertEqual(client.get("/health").status_code, 200)
        finally:
            app.state.engine.dispose()


if __name__ == "__main__":
    unittest.main()
