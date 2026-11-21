"""FR-15/A11: токен Яндекс.Диска и облачные оригиналы. HTTP не ходит в сеть.

Подменяются `yadisk._upload_href`, `upload_file`, `delete_file` и
`httpx.put/delete`; реальный токен не нужен.
"""
import contextlib
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Document, Integration, User, utcnow
from app.backend.routers import documents

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}
ALICE_TOKEN = "y0_AgAlice-token-1234"
BOB_TOKEN = "y0_AgBob-token-567890"
BIG_BYTES = 20 * 1024 * 1024 + 1
MD = "---\ntitle: Большая заметка\n---\n\nТекст про бюджет проекта.\n"
OAUTH_ENV = {
    "YANDEX_CLIENT_ID": "client-id",
    "YANDEX_CLIENT_SECRET": "client-secret",
    "YANDEX_REDIRECT_URI": "http://127.0.0.1:8000/api/settings/yadisk/callback",
}


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
        # Проверка у Яндекса проверяется отдельным тестом; здесь — без сети.
        with mock.patch.object(yadisk, "validate_token"):
            return self._ok(
                client.put("/api/settings/yadisk", json={"token": token})
            )

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
            stored = json.loads(yadisk.decrypt_token(integration.token_enc))
            self.assertEqual(stored["access_token"], ALICE_TOKEN)
            self.assertEqual(stored["refresh_token"], "")

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

    def test_invalid_token_is_422(self) -> None:
        for token in (
            "",
            "   ",
            "ab",
            "y0_" + "a" * 16,  # 19 символов — короче минимума
            "y0_" + "a" * 30 + " ",
            "y0_" + "a" * 30 + "\n",
        ):
            with self.subTest(token=token):
                response = self.alice.put(
                    "/api/settings/yadisk", json={"token": token}
                )
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            self.alice.put("/api/settings/yadisk", json={}).status_code, 422
        )

    def test_mask_token_hides_sensitive_part(self) -> None:
        self.assertEqual(yadisk.mask_token("ab"), "***")
        self.assertEqual(yadisk.mask_token("y0_short"), "***")
        masked = yadisk.mask_token(ALICE_TOKEN)
        self.assertEqual(masked, "***1234")
        self.assertNotIn(ALICE_TOKEN, masked)

    def test_settings_put_validates_token(self) -> None:
        # 200 от Яндекса: токен проверен, зашифрован и сохранён.
        with mock.patch.object(
            yadisk.httpx, "get", return_value=httpx.Response(200)
        ) as check:
            body = self._ok(
                self.alice.put(
                    "/api/settings/yadisk", json={"token": ALICE_TOKEN}
                )
            )
        self.assertEqual(body, {"configured": True, "masked": "***1234"})
        self.assertEqual(check.call_args.args[0], yadisk.DISK_URL)
        self.assertEqual(
            check.call_args.kwargs["headers"],
            {"Authorization": f"OAuth {ALICE_TOKEN}"},
        )
        with self.app.state.SessionLocal() as db:
            integration = (
                db.query(Integration)
                .filter_by(owner_id=self.alice_id, kind="yadisk")
                .one()
            )
            self.assertEqual(
                yadisk.access_from_raw(
                    yadisk.decrypt_token(integration.token_enc)
                ),
                ALICE_TOKEN,
            )

        # 401/403: токен отклонён — 422, в БД ничего не пишем.
        for code in (401, 403):
            with self.subTest(code=code):
                with mock.patch.object(
                    yadisk.httpx, "get", return_value=httpx.Response(code)
                ):
                    response = self.bob.put(
                        "/api/settings/yadisk", json={"token": BOB_TOKEN}
                    )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(
                    response.json()["detail"], "Yandex rejected the token"
                )
                self.assertNotIn(BOB_TOKEN, response.text)
                with self.app.state.SessionLocal() as db:
                    self.assertEqual(
                        db.query(Integration)
                        .filter_by(owner_id=self.bob_id)
                        .count(),
                        0,
                    )

        # Сеть/таймаут: проверить нельзя — 503, в БД ничего не пишем.
        with mock.patch.object(
            yadisk.httpx, "get", side_effect=httpx.ConnectError("down")
        ):
            response = self.alice.put(
                "/api/settings/yadisk", json={"token": BOB_TOKEN}
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"], "cannot verify token with Yandex"
        )
        with self.app.state.SessionLocal() as db:
            # Прежний токен A не перезаписан отклонённым.
            integration = (
                db.query(Integration)
                .filter_by(owner_id=self.alice_id, kind="yadisk")
                .one()
            )
            self.assertEqual(
                yadisk.access_from_raw(
                    yadisk.decrypt_token(integration.token_enc)
                ),
                ALICE_TOKEN,
            )

    def test_short_stored_token_is_masked_fully(self) -> None:
        # Запись могла остаться с прошлых версий: GET не должен её раскрывать.
        with self.app.state.SessionLocal() as db:
            db.add(
                Integration(
                    owner_id=self.alice_id,
                    kind="yadisk",
                    token_enc=yadisk.encrypt_token("ab"),
                )
            )
            db.commit()
        body = self._ok(self.alice.get("/api/settings/yadisk"))
        self.assertEqual(body, {"configured": True, "masked": "***"})

    def test_missing_fernet_key_is_503(self) -> None:
        with (
            mock.patch.object(yadisk, "validate_token"),
            mock.patch.dict(os.environ, {"ATLAS_FERNET_KEY": ""}),
        ):
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
            self._ok(self.bob.get("/api/settings/yadisk"))["masked"], "***7890"
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
        # Две папки (сначала /atlas, затем /atlas/<owner>), потом файл.
        self.assertEqual(put.call_count, 3)
        folder_calls = put.call_args_list[:2]
        self.assertEqual(
            [call.kwargs["params"] for call in folder_calls],
            [{"path": "/atlas"}, {"path": f"/atlas/{self.alice_id}"}],
        )
        for call in folder_calls:
            self.assertEqual(call.args[0], yadisk.API_URL)
            self.assertEqual(
                call.kwargs["headers"],
                {"Authorization": f"OAuth {ALICE_TOKEN}"},
            )
        file_call = put.call_args_list[2]
        self.assertEqual(file_call.args[0], "https://uploader.example/f")
        self.assertEqual(file_call.kwargs["timeout"], yadisk.TIMEOUT_SECONDS)
        self.assertTrue(path.is_file())  # локальная копия не теряется

    def test_ensure_folder_idempotent_and_auth_errors(self) -> None:
        for code in (201, 409):
            with self.subTest(code=code):
                with mock.patch.object(
                    yadisk.httpx, "put", return_value=httpx.Response(code)
                ) as put:
                    yadisk.ensure_folder(ALICE_TOKEN, "/atlas")
                self.assertEqual(put.call_args.args[0], yadisk.API_URL)
                self.assertEqual(
                    put.call_args.kwargs["params"], {"path": "/atlas"}
                )
                self.assertEqual(
                    put.call_args.kwargs["headers"],
                    {"Authorization": f"OAuth {ALICE_TOKEN}"},
                )
        for code in (401, 403):
            with self.subTest(code=code):
                with mock.patch.object(
                    yadisk.httpx, "put", return_value=httpx.Response(code)
                ):
                    with self.assertRaises(yadisk.YadiskUnauthorized):
                        yadisk.ensure_folder(ALICE_TOKEN, "/atlas")
        with mock.patch.object(
            yadisk.httpx, "put", return_value=httpx.Response(500)
        ):
            with self.assertRaises(yadisk.YadiskError):
                yadisk.ensure_folder(ALICE_TOKEN, "/atlas")
        with mock.patch.object(
            yadisk.httpx, "put", side_effect=httpx.ConnectError("down")
        ):
            with self.assertRaises(yadisk.YadiskError):
                yadisk.ensure_folder(ALICE_TOKEN, "/atlas")

    def test_store_original_folder_auth_error_keeps_local(self) -> None:
        self._put_token(self.alice)
        document_id = self._new_document(self.alice_id)
        path = self._big_file(document_id)
        with (
            mock.patch.object(
                yadisk.httpx, "put", return_value=httpx.Response(401)
            ),
            mock.patch.object(yadisk, "upload_file") as upload,
        ):
            with self.app.state.SessionLocal() as db:
                stored = yadisk.store_original(
                    db,
                    db.get(User, self.alice_id),
                    db.get(Document, document_id),
                    path,
                )
        self.assertFalse(stored)
        upload.assert_not_called()
        self.assertTrue(path.is_file())
        with self.app.state.SessionLocal() as db:
            document = db.get(Document, document_id)
            self.assertEqual(document.storage, "local")
            self.assertEqual(document.error, "yandex disk upload failed")

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
        with (
            mock.patch.object(yadisk, "ensure_folder"),
            mock.patch.object(
                yadisk, "_upload_href", side_effect=yadisk.YadiskError("boom")
            ),
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
            mock.patch.object(yadisk, "ensure_folder") as ensure,
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
        self.assertEqual(
            [call.args[1] for call in ensure.call_args_list],
            ["/atlas", f"/atlas/{self.alice_id}"],
        )
        self.assertTrue(
            (self.storage_dir / self.alice_id / f"{document_id}.md").is_file()
        )

        with mock.patch.object(yadisk, "delete_file") as delete:
            self.assertEqual(
                self.alice.delete(f"/api/documents/{document_id}").status_code,
                204,
            )
        delete.assert_called_once_with(ALICE_TOKEN, remote)

    # ---------- F4: скачивание облачного оригинала ----------

    def test_download_file_streams_href_body(self) -> None:
        dest = Path(self.tmp.name) / "downloaded.md"
        href = "https://downloader.example/f"
        with (
            mock.patch.object(
                yadisk.httpx,
                "get",
                return_value=httpx.Response(200, json={"href": href}),
            ) as link,
            mock.patch.object(
                yadisk.httpx,
                "stream",
                return_value=contextlib.nullcontext(
                    httpx.Response(200, content=b"body")
                ),
            ) as stream,
        ):
            yadisk.download_file(ALICE_TOKEN, "/atlas/a/1.md", dest)
        self.assertEqual(dest.read_bytes(), b"body")
        link.assert_called_once()
        self.assertEqual(link.call_args.args[0], f"{yadisk.API_URL}/download")
        self.assertEqual(
            link.call_args.kwargs["params"], {"path": "/atlas/a/1.md"}
        )
        self.assertEqual(
            link.call_args.kwargs["headers"],
            {"Authorization": f"OAuth {ALICE_TOKEN}"},
        )
        # OAuth уходит только к API: к подписанной ссылке — без заголовка.
        stream.assert_called_once()
        self.assertEqual(stream.call_args.args[0], "GET")
        self.assertEqual(stream.call_args.args[1], href)
        self.assertNotIn("headers", stream.call_args.kwargs)

    def test_download_file_failure_leaves_no_partial_file(self) -> None:
        dest = Path(self.tmp.name) / "broken.md"
        with mock.patch.object(
            yadisk.httpx, "get", return_value=httpx.Response(404)
        ):
            with self.assertRaises(yadisk.YadiskError):
                yadisk.download_file(ALICE_TOKEN, "/atlas/a/1.md", dest)
        self.assertFalse(dest.exists())

        with (
            mock.patch.object(
                yadisk.httpx,
                "get",
                return_value=httpx.Response(200, json={"href": "https://x/f"}),
            ),
            mock.patch.object(
                yadisk.httpx,
                "stream",
                return_value=contextlib.nullcontext(httpx.Response(500)),
            ),
        ):
            with self.assertRaises(yadisk.YadiskError):
                yadisk.download_file(ALICE_TOKEN, "/atlas/a/1.md", dest)
        self.assertFalse(dest.exists())

        # Потолок размера: недокачанный файл удаляется.
        with (
            mock.patch.object(
                yadisk.httpx,
                "get",
                return_value=httpx.Response(200, json={"href": "https://x/f"}),
            ),
            mock.patch.object(config, "MAX_UPLOAD_BYTES", 3),
            mock.patch.object(
                yadisk.httpx,
                "stream",
                return_value=contextlib.nullcontext(
                    httpx.Response(200, content=b"12345")
                ),
            ),
        ):
            with self.assertRaises(yadisk.YadiskError):
                yadisk.download_file(ALICE_TOKEN, "/atlas/a/1.md", dest)
        self.assertFalse(dest.exists())

    def _ensure(self, document_id: int) -> Path | None:
        with self.app.state.SessionLocal() as db:
            return yadisk.ensure_local_original(
                db,
                db.get(User, self.alice_id),
                db.get(Document, document_id),
            )

    def test_ensure_local_original_downloads_when_missing(self) -> None:
        self._put_token(self.alice)
        remote = f"/atlas/{self.alice_id}/21.md"
        document_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref=f"disk:{remote}"
        )

        def fake_download(token, path, dest):
            dest.write_bytes(MD.encode("utf-8"))

        with mock.patch.object(
            yadisk, "download_file", side_effect=fake_download
        ) as download:
            path = self._ensure(document_id)
        expected = self.storage_dir / self.alice_id / f"{document_id}.md"
        download.assert_called_once_with(ALICE_TOKEN, remote, expected)
        self.assertEqual(path, expected)
        self.assertEqual(path.read_bytes(), MD.encode("utf-8"))

    def test_ensure_local_original_prefers_existing_copy(self) -> None:
        document_id = self._new_document(
            self.alice_id,
            storage="yandex",
            storage_ref="disk:/atlas/x/22.md",
        )
        existing = self.storage_dir / self.alice_id / f"{document_id}.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"local")
        with mock.patch.object(yadisk, "download_file") as download:
            path = self._ensure(document_id)
        download.assert_not_called()
        self.assertEqual(path, existing)

    def test_ensure_local_original_returns_none(self) -> None:
        # Локальный документ без файла: скачивать неоткуда.
        local_id = self._new_document(self.alice_id)
        with mock.patch.object(yadisk, "download_file") as download:
            self.assertIsNone(self._ensure(local_id))
        download.assert_not_called()
        # Облачный документ без токена: в сеть не идём.
        remote_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref="disk:/atlas/x/23.md"
        )
        with mock.patch.object(yadisk, "download_file") as download:
            self.assertIsNone(self._ensure(remote_id))
        download.assert_not_called()

    def test_cloud_original_served_and_reprocessed(self) -> None:
        self._put_token(self.alice)
        remote = f"/atlas/{self.alice_id}/24.md"
        document_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref=f"disk:{remote}"
        )

        def fake_download(token, path, dest):
            dest.write_bytes(MD.encode("utf-8"))

        with mock.patch.object(
            yadisk, "download_file", side_effect=fake_download
        ) as download:
            original = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.content, MD.encode("utf-8"))
        download.assert_called_once_with(
            ALICE_TOKEN,
            remote,
            self.storage_dir / self.alice_id / f"{document_id}.md",
        )

        # Копия теперь локальная: повторная выдача без сети.
        with mock.patch.object(yadisk, "download_file") as again:
            self.assertEqual(
                self.alice.get(f"/api/documents/{document_id}/file").status_code,
                200,
            )
        again.assert_not_called()

        reprocessed = self.alice.post(
            f"/api/documents/{document_id}/reprocess"
        )
        self.assertEqual(reprocessed.status_code, 200, reprocessed.text)
        self.assertEqual(reprocessed.json()["status"], "ready")
        self.assertIn(
            "бюджет",
            self.alice.get(f"/api/documents/{document_id}/content").text,
        )

    def test_cloud_original_unavailable_is_409(self) -> None:
        self._put_token(self.alice)
        remote = f"/atlas/{self.alice_id}/25.md"
        document_id = self._new_document(
            self.alice_id, storage="yandex", storage_ref=f"disk:{remote}"
        )
        with mock.patch.object(
            yadisk, "download_file", side_effect=yadisk.YadiskError("boom")
        ):
            for method, path in (
                ("get", f"/api/documents/{document_id}/file"),
                ("post", f"/api/documents/{document_id}/reprocess"),
            ):
                with self.subTest(path=path):
                    response = getattr(self.alice, method)(path)
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertIn("external storage", response.json()["detail"])

        # Без токена — тоже 409, но без сетевого вызова.
        self.assertEqual(self.alice.delete("/api/settings/yadisk").status_code, 204)
        with mock.patch.object(yadisk, "download_file") as download:
            self.assertEqual(
                self.alice.get(f"/api/documents/{document_id}/file").status_code,
                409,
            )
        download.assert_not_called()

    # ---------- F11: OAuth Яндекс.Диска ----------

    @staticmethod
    def _oauth_env():
        return mock.patch.multiple(config, **OAUTH_ENV)

    def _authorize_state(self) -> str:
        response = self.alice.get("/api/settings/yadisk/authorize")
        self.assertEqual(response.status_code, 200, response.text)
        query = parse_qs(urlparse(response.json()["url"]).query)
        return query["state"][0]

    def test_oauth_requires_env(self) -> None:
        with mock.patch.multiple(
            config,
            YANDEX_CLIENT_ID="",
            YANDEX_CLIENT_SECRET="",
            YANDEX_REDIRECT_URI=OAUTH_ENV["YANDEX_REDIRECT_URI"],
        ):
            authorize = self.alice.get("/api/settings/yadisk/authorize")
            callback = self.alice.get(
                "/api/settings/yadisk/callback",
                params={"code": "c", "state": "s"},
            )
        self.assertEqual(authorize.status_code, 503, authorize.text)
        self.assertEqual(callback.status_code, 503, callback.text)
        self.assertIn("YANDEX_CLIENT_ID", authorize.json()["detail"])

    def test_oauth_authorize_sets_state_cookie(self) -> None:
        with self._oauth_env():
            response = self.alice.get("/api/settings/yadisk/authorize")
        self.assertEqual(response.status_code, 200, response.text)
        parsed = urlparse(response.json()["url"])
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            yadisk.OAUTH_AUTHORIZE_URL,
        )
        query = parse_qs(parsed.query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], [OAUTH_ENV["YANDEX_CLIENT_ID"]])
        self.assertEqual(
            query["redirect_uri"], [OAUTH_ENV["YANDEX_REDIRECT_URI"]]
        )
        state = query["state"][0]
        self.assertEqual(response.cookies.get("yadisk_state"), state)
        set_cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Max-Age=600", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)

    def test_oauth_callback_stores_tokens(self) -> None:
        token_response = httpx.Response(
            200,
            json={
                "access_token": "new-access-token",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
            },
        )
        with self._oauth_env():
            state = self._authorize_state()
            with mock.patch.object(
                yadisk.httpx, "post", return_value=token_response
            ) as post:
                response = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state},
                    follow_redirects=False,
                )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(response.headers["location"], "/?yadisk=connected")
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], yadisk.OAUTH_TOKEN_URL)
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "grant_type": "authorization_code",
                "code": "auth-code",
                "client_id": OAUTH_ENV["YANDEX_CLIENT_ID"],
                "client_secret": OAUTH_ENV["YANDEX_CLIENT_SECRET"],
                "redirect_uri": OAUTH_ENV["YANDEX_REDIRECT_URI"],
            },
        )
        self.assertNotIn("new-access-token", response.text)
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))
        with self.app.state.SessionLocal() as db:
            integration = (
                db.query(Integration)
                .filter_by(owner_id=self.alice_id, kind="yadisk")
                .one()
            )
            tokens = json.loads(yadisk.decrypt_token(integration.token_enc))
        self.assertEqual(tokens["access_token"], "new-access-token")
        self.assertEqual(tokens["refresh_token"], "refresh-1")
        self.assertTrue(tokens["expires_at"])
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/yadisk")),
            {"configured": True, "masked": "***oken"},
        )

    def test_oauth_callback_rejects_state_mismatch(self) -> None:
        with self._oauth_env():
            state = self._authorize_state()
            with mock.patch.object(yadisk.httpx, "post") as post:
                mismatch = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state + "x"},
                    follow_redirects=False,
                )
                # Cookie погашена: повтор без неё — тоже отказ.
                no_cookie = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state},
                    follow_redirects=False,
                )
                denied = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"error": "access_denied"},
                    follow_redirects=False,
                )
        for response in (mismatch, no_cookie, denied):
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(response.headers["location"], "/?yadisk=error")
        post.assert_not_called()
        with self.app.state.SessionLocal() as db:
            self.assertEqual(
                db.query(Integration).filter_by(owner_id=self.alice_id).count(), 0
            )

    def test_oauth_callback_token_failure_returns_to_ui(self) -> None:
        with self._oauth_env():
            state = self._authorize_state()
            with mock.patch.object(
                yadisk.httpx, "post", return_value=httpx.Response(400)
            ):
                rejected = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "bad", "state": state},
                    follow_redirects=False,
                )
            state = self._authorize_state()
            with mock.patch.object(
                yadisk.httpx, "post", side_effect=httpx.ConnectError("down")
            ):
                unreachable = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "c", "state": state},
                    follow_redirects=False,
                )
        for response in (rejected, unreachable):
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(response.headers["location"], "/?yadisk=error")
        with self.app.state.SessionLocal() as db:
            self.assertEqual(
                db.query(Integration).filter_by(owner_id=self.alice_id).count(), 0
            )

    def _store_tokens(self, tokens: dict) -> None:
        with self.app.state.SessionLocal() as db:
            db.add(
                Integration(
                    owner_id=self.alice_id,
                    kind="yadisk",
                    token_enc=yadisk.encrypt_token(json.dumps(tokens)),
                )
            )
            db.commit()

    def test_token_for_refreshes_expiring_access(self) -> None:
        self._store_tokens(
            {
                "access_token": "old-access",
                "refresh_token": "refresh-1",
                "expires_at": (utcnow() + timedelta(seconds=30)).isoformat(),
            }
        )
        refreshed = httpx.Response(
            200, json={"access_token": "new-access", "expires_in": 3600}
        )
        with self._oauth_env(), mock.patch.object(
            yadisk.httpx, "post", return_value=refreshed
        ) as post:
            with self.app.state.SessionLocal() as db:
                token = yadisk._token_for(db, self.alice_id)
                integration = (
                    db.query(Integration)
                    .filter_by(owner_id=self.alice_id, kind="yadisk")
                    .one()
                )
                stored = json.loads(yadisk.decrypt_token(integration.token_enc))
        self.assertEqual(token, "new-access")
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "grant_type": "refresh_token",
                "refresh_token": "refresh-1",
                "client_id": OAUTH_ENV["YANDEX_CLIENT_ID"],
                "client_secret": OAUTH_ENV["YANDEX_CLIENT_SECRET"],
            },
        )
        self.assertEqual(stored["access_token"], "new-access")
        self.assertEqual(stored["refresh_token"], "refresh-1")

    def test_token_for_uses_valid_json_and_old_raw(self) -> None:
        self._store_tokens(
            {
                "access_token": "valid-access",
                "refresh_token": "refresh-1",
                "expires_at": (utcnow() + timedelta(hours=1)).isoformat(),
            }
        )
        with mock.patch.object(yadisk.httpx, "post") as post:
            with self.app.state.SessionLocal() as db:
                self.assertEqual(
                    yadisk._token_for(db, self.alice_id), "valid-access"
                )
        post.assert_not_called()

        # Старый формат — сырой токен, обновлять нечего.
        with self.app.state.SessionLocal() as db:
            db.query(Integration).filter_by(owner_id=self.alice_id).delete()
            db.add(
                Integration(
                    owner_id=self.alice_id,
                    kind="yadisk",
                    token_enc=yadisk.encrypt_token("raw-token"),
                )
            )
            db.commit()
        with mock.patch.object(yadisk.httpx, "post") as post:
            with self.app.state.SessionLocal() as db:
                self.assertEqual(yadisk._token_for(db, self.alice_id), "raw-token")
        post.assert_not_called()

    def test_token_for_keeps_access_when_refresh_fails(self) -> None:
        self._store_tokens(
            {
                "access_token": "old-access",
                "refresh_token": "refresh-1",
                "expires_at": utcnow().isoformat(),
            }
        )
        with mock.patch.object(
            yadisk.httpx, "post", side_effect=httpx.ConnectError("down")
        ):
            with self.app.state.SessionLocal() as db:
                self.assertEqual(
                    yadisk._token_for(db, self.alice_id), "old-access"
                )


if __name__ == "__main__":
    unittest.main()
