"""FR-15/A11: токен Яндекс.Диска и облачные оригиналы. HTTP не ходит в сеть.

Подменяются `yadisk._upload_href`, `upload_file`, `delete_file` и
`httpx.put/delete`; реальный токен не нужен.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Document, Integration, User
from app.backend.routers import documents

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}
ALICE_TOKEN = "y0_AgAlice-token-1234"
BOB_TOKEN = "y0_AgBob-token-5678"
BIG_BYTES = 20 * 1024 * 1024 + 1
MD = "---\ntitle: Большая заметка\n---\n\nТекст про бюджет проекта.\n"


class YadiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage_dir = Path(self.tmp.name) / "storage"
        url = f"sqlite:///{(Path(self.tmp.name) / 'test.db').as_posix()}"
        self.app = create_app(url)
        self.engine = self.app.state.engine
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with self.app.state.SessionLocal() as db:
            alice = User(
                username=ALICE["username"],
                password_hash=hash_password(ALICE["password"]),
            )
            bob = User(
                username=BOB["username"],
                password_hash=hash_password(BOB["password"]),
            )
            db.add_all([alice, bob])
            db.commit()
            self.alice_id, self.bob_id = alice.id, bob.id

        patcher = mock.patch.object(config, "STORAGE_DIR", self.storage_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

        previous_key = os.environ.get("ATLAS_FERNET_KEY")
        os.environ["ATLAS_FERNET_KEY"] = Fernet.generate_key().decode()
        self.addCleanup(self._restore_key, previous_key)

        self.alice = TestClient(self.app)
        self.bob = TestClient(self.app)
        self.addCleanup(self.alice.close)
        self.addCleanup(self.bob.close)
        self._login(self.alice, ALICE)
        self._login(self.bob, BOB)

    # ---------- helpers ----------

    @staticmethod
    def _restore_key(previous: str | None) -> None:
        if previous is None:
            os.environ.pop("ATLAS_FERNET_KEY", None)
        else:
            os.environ["ATLAS_FERNET_KEY"] = previous

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post("/api/auth/login", json=user)
        self.assertEqual(response.status_code, 200, response.text)

    def _ok(self, response, code: int = 200) -> dict:
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _put_token(self, client: TestClient, token: str = ALICE_TOKEN) -> dict:
        return self._ok(client.put("/api/settings/yadisk", json={"token": token}))

    def _new_document(
        self, owner_id: str, storage: str = "local", storage_ref: str | None = None
    ) -> int:
        with self.app.state.SessionLocal() as db:
            document = Document(
                owner_id=owner_id,
                title="big.md",
                mime="text/markdown",
                size_bytes=BIG_BYTES,
                storage=storage,
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            document.storage_ref = storage_ref or f"{owner_id}/{document.id}.md"
            db.commit()
            return document.id

    def _big_file(self, document_id: int) -> Path:
        """Разреженный файл нужного размера: содержимое не пишется на диск."""
        path = self.storage_dir / self.alice_id / f"{document_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.truncate(BIG_BYTES)
        return path

    # ---------- настройки ----------

    def test_settings_put_get_delete(self) -> None:
        self.assertEqual(
            self._put_token(self.alice),
            {"configured": True, "masked": "***1234"},
        )
        fetched = self.alice.get("/api/settings/yadisk")
        self.assertEqual(
            self._ok(fetched), {"configured": True, "masked": "***1234"}
        )
        self.assertNotIn(ALICE_TOKEN, fetched.text)

        with self.app.state.SessionLocal() as db:
            integration = (
                db.query(Integration)
                .filter_by(owner_id=self.alice_id, kind="yadisk")
                .one()
            )
            self.assertNotIn(ALICE_TOKEN, integration.token_enc or "")
            self.assertEqual(
                yadisk.decrypt_token(integration.token_enc), ALICE_TOKEN
            )

        self.assertEqual(
            self.alice.delete("/api/settings/yadisk").status_code, 204
        )
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )
        with self.app.state.SessionLocal() as db:
            self.assertEqual(
                db.query(Integration).filter_by(owner_id=self.alice_id).count(), 0
            )

    def test_empty_token_is_422(self) -> None:
        for token in ("", "   "):
            with self.subTest(token=token):
                response = self.alice.put(
                    "/api/settings/yadisk", json={"token": token}
                )
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            self.alice.put("/api/settings/yadisk", json={}).status_code, 422
        )

    def test_missing_fernet_key_is_503(self) -> None:
        with mock.patch.dict(os.environ, {"ATLAS_FERNET_KEY": ""}):
            response = self.alice.put(
                "/api/settings/yadisk", json={"token": ALICE_TOKEN}
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("ATLAS_FERNET_KEY", response.json()["detail"])

        self._put_token(self.alice)
        with mock.patch.dict(os.environ, {"ATLAS_FERNET_KEY": ""}):
            self.assertEqual(
                self.alice.get("/api/settings/yadisk").status_code, 503
            )

    def test_settings_are_isolated_between_users(self) -> None:
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )
        self._put_token(self.alice)
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )

        self._put_token(self.bob, BOB_TOKEN)
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/yadisk"))["masked"], "***1234"
        )
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/yadisk"))["masked"], "***5678"
        )

        self.bob.delete("/api/settings/yadisk")
        self.assertFalse(self._ok(self.bob.get("/api/settings/yadisk"))["configured"])
        self.assertTrue(self._ok(self.alice.get("/api/settings/yadisk"))["configured"])

    # ---------- store_original ----------

    def test_store_original_uploads_big_file(self) -> None:
        self._put_token(self.alice)
        document_id = self._new_document(self.alice_id)
        path = self._big_file(document_id)
        remote = f"/atlas/{self.alice_id}/{document_id}.md"
        with (
            mock.patch.object(
                yadisk, "_upload_href", return_value="https://uploader.example/f"
            ) as href,
            mock.patch.object(
                yadisk.httpx, "put", return_value=httpx.Response(201)
            ) as put,
        ):
            with self.app.state.SessionLocal() as db:
                stored = yadisk.store_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                    path,
                )
                document = db.get(Document, document_id)
                self.assertTrue(stored)
                self.assertEqual(document.storage, "yandex")
                self.assertEqual(document.storage_ref, f"disk:{remote}")
        href.assert_called_once_with(ALICE_TOKEN, remote)
        self.assertEqual(put.call_count, 1)
        self.assertEqual(
            put.call_args.kwargs["timeout"], yadisk.TIMEOUT_SECONDS
        )
        self.assertTrue(path.is_file())  # локальная копия не теряется

    def test_store_original_without_token_keeps_local(self) -> None:
        document_id = self._new_document(self.alice_id)
        path = self._big_file(document_id)
        with mock.patch.object(yadisk, "upload_file") as upload:
            with self.app.state.SessionLocal() as db:
                stored = yadisk.store_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                    path,
                )
        self.assertFalse(stored)
        upload.assert_not_called()
        with self.app.state.SessionLocal() as db:
            document = db.get(Document, document_id)
            self.assertEqual(document.storage, "local")
            self.assertIsNone(document.error)
        self.assertTrue(path.is_file())

    def test_store_original_api_error_keeps_local(self) -> None:
        self._put_token(self.alice)
        document_id = self._new_document(self.alice_id)
        path = self._big_file(document_id)
        with mock.patch.object(
            yadisk, "_upload_href", side_effect=yadisk.YadiskError("boom")
        ):
            with self.app.state.SessionLocal() as db:
                stored = yadisk.store_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                    path,
                )
        self.assertFalse(stored)
        self.assertTrue(path.is_file())
        with self.app.state.SessionLocal() as db:
            document = db.get(Document, document_id)
            self.assertEqual(document.storage, "local")
            self.assertEqual(document.error, "yandex disk upload failed")

    # ---------- delete_original ----------

    def test_delete_original_calls_api(self) -> None:
        self._put_token(self.alice)
        remote = f"/atlas/{self.alice_id}/7.md"
        document_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref=f"disk:{remote}"
        )
        with mock.patch.object(
            yadisk.httpx, "delete", return_value=httpx.Response(204)
        ) as delete:
            with self.app.state.SessionLocal() as db:
                removed = yadisk.delete_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                )
        self.assertTrue(removed)
        delete.assert_called_once()
        self.assertEqual(
            delete.call_args.kwargs["params"],
            {"path": remote, "permanently": "true"},
        )
        self.assertEqual(
            delete.call_args.kwargs["headers"],
            {"Authorization": f"OAuth {ALICE_TOKEN}"},
        )

    def test_delete_original_error_does_not_raise(self) -> None:
        self._put_token(self.alice)
        remote = f"/atlas/{self.alice_id}/8.md"
        document_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref=f"disk:{remote}"
        )
        with mock.patch.object(
            yadisk.httpx, "delete", side_effect=httpx.ConnectError("down")
        ):
            with self.app.state.SessionLocal() as db:
                removed = yadisk.delete_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                )
        self.assertFalse(removed)
        with self.app.state.SessionLocal() as db:
            self.assertIsNotNone(db.get(Document, document_id))

        local_id = self._new_document(self.alice_id)
        with mock.patch.object(yadisk, "delete_file") as delete_file:
            with self.app.state.SessionLocal() as db:
                self.assertFalse(
                    yadisk.delete_original(
                        db,
                        db.get(User, self.alice_id),
                        db.get(Document, local_id),
                    )
                )
        delete_file.assert_not_called()

    # ---------- сквозной путь загрузки ----------

    def test_upload_over_threshold_stores_on_disk_and_delete(self) -> None:
        self._put_token(self.alice)
        with (
            mock.patch.object(documents, "YADISK_THRESHOLD", 10),
            mock.patch.object(yadisk, "upload_file") as upload,
        ):
            body = self._ok(
                self.alice.post(
                    "/api/documents",
                    files={"file": ("note.md", MD.encode("utf-8"), "text/markdown")},
                )
            )
        document_id = body["id"]
        remote = f"/atlas/{self.alice_id}/{document_id}.md"
        self.assertEqual(body["storage"], "yandex")
        self.assertEqual(body["storage_ref"], f"disk:{remote}")
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0], ALICE_TOKEN)
        self.assertEqual(upload.call_args.args[1], remote)
        self.assertTrue(
            (self.storage_dir / self.alice_id / f"{document_id}.md").is_file()
        )

        with mock.patch.object(yadisk, "delete_file") as delete:
            self.assertEqual(
                self.alice.delete(f"/api/documents/{document_id}").status_code,
                204,
            )
        delete.assert_called_once_with(ALICE_TOKEN, remote)


if __name__ == "__main__":
    unittest.main()
