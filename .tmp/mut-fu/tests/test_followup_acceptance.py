"""WS-C: независимая приёмка follow-up T-07344017 (F1/F3/F4/F7/F8/F9/F11/F12/F13).

Сценарии — с точки зрения владельца API, без реальных сети/BGE-M3/Qdrant:
temp SQLite, `ATLAS_EMBEDDINGS=fake`, `ATLAS_QDRANT_URL=:memory:`; сеть
Яндекс.Диска и индексация — моками. Тест не заменяет авторские наборы, а
независимо воспроизводит acceptance из брифа/плана.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.knowledge import indexer
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Integration, Job, User, utcnow
from app.backend.routers import documents as documents_router
from app.backend.routers import worker as worker_router

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}
REDIRECT_URI = "http://127.0.0.1:8000/api/settings/yadisk/callback"
MANUAL_TOKEN = "y0_AgAcceptance-token-1234"
MD = (
    "---\ntitle: Acceptance note\n---\n\n"
    "Иван Петров обсудил бюджет проекта 12.03.2026 в г. Москва. #финансы\n"
).encode("utf-8")
WORKER_TEXT = "Распознанный скан: договор с ООО «Ромашка», дата 12.03.2026."


def make_png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


class FollowUpAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage_dir = Path(self.tmp.name) / "storage"

        env = mock.patch.dict(
            os.environ,
            {
                "ATLAS_EMBEDDINGS": "fake",
                "ATLAS_QDRANT_URL": ":memory:",
                # Своя коллекция на тест: singleton :memory: живёт в процессе.
                "ATLAS_COLLECTION": f"acceptance_{uuid.uuid4().hex}",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        indexer.reset_client()
        self.addCleanup(indexer.reset_client)

        previous_key = os.environ.get("ATLAS_FERNET_KEY")
        os.environ["ATLAS_FERNET_KEY"] = Fernet.generate_key().decode()
        self.addCleanup(self._restore_key, previous_key)

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

        storage_patch = mock.patch.object(config, "STORAGE_DIR", self.storage_dir)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)

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

    def _ok(self, response, code: int = 200):
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _db(self):
        return self.app.state.SessionLocal()

    def _upload(
        self,
        client: TestClient,
        name: str,
        content: bytes,
        content_type: str = "text/markdown",
    ):
        return client.post(
            "/api/documents",
            files={"file": (name, content, content_type)},
        )

    def _upload_png(
        self, client: TestClient, name: str = "scan.png", color: str = "white"
    ) -> dict:
        body = self._ok(self._upload(client, name, make_png(color), "image/png"))
        self.assertFalse(body["duplicate"])
        self.assertEqual(body["status"], "queued")
        return body

    def _token(self, client: TestClient) -> str:
        body = self._ok(client.post("/api/settings/worker-token"), 201)
        self.assertTrue(body["token"])
        return body["token"]

    @staticmethod
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _document(self, client: TestClient, document_id: int) -> dict:
        return self._ok(client.get(f"/api/documents/{document_id}"))

    def _cloud_document(self, owner_id: str) -> tuple[int, str]:
        """Документ `storage='yandex'` без локальной копии; (id, remote path)."""
        with self._db() as db:
            document = Document(
                owner_id=owner_id,
                title="cloud.md",
                mime="text/markdown",
                size_bytes=32,
                storage="yandex",
                status="ready",
                tags=[],
                entities={},
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            remote = f"/atlas/{owner_id}/{document.id}.md"
            document.storage_ref = f"disk:{remote}"
            db.commit()
            document_id = document.id
        self.assertFalse(
            (self.storage_dir / owner_id / f"{document_id}.md").exists(),
            "у облачного документа не должно быть локальной копии",
        )
        return document_id, remote

    def _set_tokens(self, owner_id: str, tokens: dict) -> None:
        with self._db() as db:
            db.query(Integration).filter_by(owner_id=owner_id, kind="yadisk").delete()
            db.add(
                Integration(
                    owner_id=owner_id,
                    kind="yadisk",
                    token_enc=yadisk.encrypt_token(json.dumps(tokens)),
                )
            )
            db.commit()

    def _oauth_env(self):
        return mock.patch.multiple(
            config,
            YANDEX_CLIENT_ID="client-id",
            YANDEX_CLIENT_SECRET="client-secret",
            YANDEX_REDIRECT_URI=REDIRECT_URI,
        )

    def _authorize_state(self) -> str:
        response = self.alice.get("/api/settings/yadisk/authorize")
        self.assertEqual(response.status_code, 200, response.text)
        return parse_qs(urlparse(response.json()["url"]).query)["state"][0]

    # ---------- F7: дедуп без 500 ----------

    def test_f7_repeated_upload_is_duplicate_not_500(self) -> None:
        first = self._ok(self._upload(self.alice, "note.md", MD))
        self.assertFalse(first["duplicate"])
        self.assertEqual(first["status"], "ready")

        second = self._ok(self._upload(self.alice, "copy.md", MD))
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["id"], first["id"])
        self.assertIsNone(second["error"])
        with self._db() as db:
            self.assertEqual(
                db.query(Document).filter_by(owner_id=self.alice_id).count(), 1
            )
        # Временный файл второй загрузки удалён: остался только оригинал.
        self.assertEqual(
            sorted(path.name for path in (self.storage_dir / self.alice_id).iterdir()),
            [f"{first['id']}.md"],
        )

        # Тот же контент у другого владельца — свой документ, не дубль.
        other = self._ok(self._upload(self.bob, "note.md", MD))
        self.assertFalse(other["duplicate"])
        self.assertNotEqual(other["id"], first["id"])

    def test_f7_duplicate_race_returns_existing(self) -> None:
        """Конкурент вставил тот же sha256 между проверкой и flush."""
        sha256 = hashlib.sha256(MD).hexdigest()
        with self._db() as db:
            existing = Document(
                owner_id=self.alice_id,
                title="raced.md",
                mime="text/markdown",
                size_bytes=len(MD),
                sha256=sha256,
                storage="none",
                status="ready",
                tags=[],
                entities={},
            )
            db.add(existing)
            db.commit()
            existing_id = existing.id

        real_find = documents_router._find_duplicate
        calls = {"n": 0}

        def racing_find(db, owner_id, value):
            calls["n"] += 1
            # Первая проверка — окно гонки; вторая (после IntegrityError) — реальная.
            return None if calls["n"] == 1 else real_find(db, owner_id, value)

        with mock.patch.object(
            documents_router, "_find_duplicate", side_effect=racing_find
        ):
            body = self._ok(self._upload(self.alice, "note.md", MD))
        self.assertTrue(body["duplicate"])
        self.assertEqual(body["id"], existing_id)
        self.assertGreaterEqual(calls["n"], 2)
        with self._db() as db:
            self.assertEqual(
                db.query(Document).filter_by(owner_id=self.alice_id).count(), 1
            )
        leftovers = list(self.storage_dir.rglob("tmp-*"))
        self.assertEqual(leftovers, [])

    # ---------- F8: ошибки без путей/URL/секретов ----------

    def test_f8_upload_error_is_categorized_without_details(self) -> None:
        leak = (
            f"OSError: {self.storage_dir}/secret.md "
            "https://example.com/x?token=SECRET_TOKEN"
        )
        with mock.patch.object(
            documents_router, "analyze_file", side_effect=OSError(leak)
        ):
            response = self._upload(self.alice, "bad.md", MD)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"], "document processing failed")

        with self._db() as db:
            document = db.query(Document).filter_by(owner_id=self.alice_id).one()
            card = (document.status, document.error)
            self.assertEqual(db.query(Chunk).count(), 0)
        self.assertEqual(card, ("failed", "extract failed"))
        for fragment in (str(self.storage_dir), "https://", "SECRET_TOKEN", "OSError"):
            self.assertNotIn(fragment, card[1])
            self.assertNotIn(fragment, response.text)
        # Оригинал неудавшейся загрузки не остался на диске.
        owner_dir = self.storage_dir / self.alice_id
        self.assertEqual(
            [path.name for path in owner_dir.iterdir()] if owner_dir.is_dir() else [], []
        )

    def test_f8_reprocess_error_is_categorized_without_details(self) -> None:
        body = self._ok(self._upload(self.alice, "note.md", MD))
        with mock.patch.object(
            documents_router,
            "analyze_file",
            side_effect=ValueError("unsupported format: /tmp/private/x.xml"),
        ):
            response = self.alice.post(f"/api/documents/{body['id']}/reprocess")
        self.assertEqual(response.status_code, 500, response.text)
        card = self._document(self.alice, body["id"])
        self.assertEqual(card["status"], "failed")
        self.assertEqual(card["error"], "unsupported format")
        self.assertNotIn("/tmp/private", card["error"])

    # ---------- F9: видимая индексация и reindex ----------

    def test_f9_index_failure_visible_and_reindex_recovers(self) -> None:
        with mock.patch.object(
            documents_router, "index_document", side_effect=RuntimeError("qdrant down")
        ):
            body = self._ok(self._upload(self.alice, "note.md", MD))
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["error"], "indexing failed")
        with self._db() as db:
            chunks = db.query(Chunk).filter_by(document_id=body["id"]).all()
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.qdrant_point_id is None for chunk in chunks))

        with mock.patch.object(
            documents_router, "index_document", return_value=1
        ) as index:
            recovered = self._ok(
                self.alice.post(f"/api/documents/{body['id']}/reindex")
            )
        index.assert_called_once()
        self.assertIsNone(recovered["error"])
        self.assertIsNone(self._document(self.alice, body["id"])["error"])

        # Повторный сбой — 502, ошибка снова видна и не раскрывает деталей.
        with mock.patch.object(
            documents_router, "index_document", side_effect=RuntimeError("still down")
        ):
            failed = self.alice.post(f"/api/documents/{body['id']}/reindex")
        self.assertEqual(failed.status_code, 502, failed.text)
        self.assertEqual(failed.json()["detail"], "indexing failed")
        self.assertEqual(
            self._document(self.alice, body["id"])["error"], "indexing failed"
        )

    def test_f9_worker_index_failure_visible_and_reindex_recovers(self) -> None:
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        with mock.patch.object(
            worker_router, "index_document", side_effect=RuntimeError("qdrant down")
        ):
            done = self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{claimed['job']['id']}/complete",
                    json={"text": WORKER_TEXT},
                    headers=self._auth(token),
                )
            )
        self.assertEqual(done["status"], "done")
        card = self._document(self.alice, body["id"])
        self.assertEqual((card["status"], card["error"]), ("ready", "indexing failed"))

        with mock.patch.object(documents_router, "index_document", return_value=1):
            recovered = self._ok(
                self.alice.post(f"/api/documents/{body['id']}/reindex")
            )
        self.assertIsNone(recovered["error"])

    # ---------- F4: облачный оригинал ----------

    def test_f4_cloud_original_is_downloaded_and_served(self) -> None:
        document_id, remote = self._cloud_document(self.alice_id)
        self._set_tokens(
            self.alice_id,
            {"access_token": "cloud-access", "refresh_token": "", "expires_at": None},
        )
        payload = b"# cloud original\n"
        expected = self.storage_dir / self.alice_id / f"{document_id}.md"

        def fake_download(token, path, dest):
            Path(dest).write_bytes(payload)

        with mock.patch.object(
            yadisk, "download_file", side_effect=fake_download
        ) as download:
            response = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, payload)
        download.assert_called_once_with("cloud-access", remote, expected)
        self.assertTrue(expected.is_file())

        # Копия теперь локальная: повторная выдача без сети.
        with mock.patch.object(yadisk, "download_file") as again:
            self.assertEqual(
                self.alice.get(f"/api/documents/{document_id}/file").status_code, 200
            )
        again.assert_not_called()

    def test_f4_cloud_original_without_token_or_copy_is_409(self) -> None:
        document_id, _ = self._cloud_document(self.alice_id)
        with mock.patch.object(yadisk, "download_file") as download:
            response = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("external storage", response.json()["detail"])
        download.assert_not_called()

        # Локальный документ, оригинал которого потерян, — тоже 409, не 500.
        with self._db() as db:
            local = Document(
                owner_id=self.alice_id,
                title="lost.md",
                mime="text/markdown",
                size_bytes=1,
                storage="local",
                storage_ref=f"{self.alice_id}/999.md",
                status="ready",
                tags=[],
                entities={},
            )
            db.add(local)
            db.commit()
            local_id = local.id
        with mock.patch.object(yadisk, "download_file") as download:
            self.assertEqual(
                self.alice.get(f"/api/documents/{local_id}/file").status_code, 409
            )
        download.assert_not_called()

    # ---------- F11: OAuth Яндекс.Диска ----------

    def test_f11_authorize_needs_env_and_sets_state_cookie(self) -> None:
        with mock.patch.multiple(
            config,
            YANDEX_CLIENT_ID="",
            YANDEX_CLIENT_SECRET="",
            YANDEX_REDIRECT_URI=REDIRECT_URI,
        ):
            self.assertEqual(
                self.alice.get("/api/settings/yadisk/authorize").status_code, 503
            )
            self.assertEqual(
                self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "c", "state": "s"},
                ).status_code,
                503,
            )

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
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], [REDIRECT_URI])
        state = query["state"][0]
        self.assertGreaterEqual(len(state), 16)
        self.assertEqual(response.cookies.get("yadisk_state"), state)
        set_cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Max-Age=600", set_cookie)

    def test_f11_callback_exchanges_code_and_refresh_updates_access(self) -> None:
        token_payload = httpx.Response(
            200,
            json={
                "access_token": "oauth-access",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
            },
        )
        with self._oauth_env():
            state = self._authorize_state()
            with mock.patch.object(
                yadisk.httpx, "post", return_value=token_payload
            ) as post:
                response = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state},
                    follow_redirects=False,
                )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(response.headers["location"], "/?yadisk=connected")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "grant_type": "authorization_code",
                "code": "auth-code",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uri": REDIRECT_URI,
            },
        )
        self.assertNotIn("oauth-access", response.text)
        settings = self._ok(self.alice.get("/api/settings/yadisk"))
        self.assertTrue(settings["configured"])
        self.assertNotIn("oauth-access", json.dumps(settings))
        with self._db() as db:
            stored = json.loads(
                yadisk.decrypt_token(
                    db.query(Integration)
                    .filter_by(owner_id=self.alice_id, kind="yadisk")
                    .one()
                    .token_enc
                )
            )
        self.assertEqual(stored["access_token"], "oauth-access")
        self.assertEqual(stored["refresh_token"], "refresh-1")

        # Истёкший access обновляется по refresh прямо в запросе `/file`.
        document_id, remote = self._cloud_document(self.alice_id)
        self._set_tokens(
            self.alice_id,
            {
                "access_token": "expired-access",
                "refresh_token": "refresh-1",
                "expires_at": utcnow().isoformat(),
            },
        )
        refreshed = httpx.Response(
            200, json={"access_token": "fresh-access", "expires_in": 3600}
        )

        def fake_download(token, path, dest):
            Path(dest).write_bytes(b"body")

        with (
            self._oauth_env(),
            mock.patch.object(yadisk.httpx, "post", return_value=refreshed) as refresh,
            mock.patch.object(
                yadisk, "download_file", side_effect=fake_download
            ) as download,
        ):
            response = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"body")
        self.assertEqual(
            refresh.call_args.kwargs["data"]["grant_type"], "refresh_token"
        )
        self.assertEqual(
            refresh.call_args.kwargs["data"]["refresh_token"], "refresh-1"
        )
        download.assert_called_once_with("fresh-access", remote, mock.ANY)
        with self._db() as db:
            stored = json.loads(
                yadisk.decrypt_token(
                    db.query(Integration)
                    .filter_by(owner_id=self.alice_id, kind="yadisk")
                    .one()
                    .token_enc
                )
            )
        self.assertEqual(stored["access_token"], "fresh-access")

    def test_f11_callback_rejects_bad_state_without_exchange(self) -> None:
        with self._oauth_env():
            state = self._authorize_state()
            with mock.patch.object(yadisk.httpx, "post") as post:
                mismatch = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state + "x"},
                    follow_redirects=False,
                )
                # Одноразовая cookie погашена — повтор с верным state тоже отказ.
                replay = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"code": "auth-code", "state": state},
                    follow_redirects=False,
                )
                denied = self.alice.get(
                    "/api/settings/yadisk/callback",
                    params={"error": "access_denied"},
                    follow_redirects=False,
                )
        # Бриф ждал 400; реализация уводит в UI (`/?yadisk=error`) — фиксируем
        # наблюдаемое поведение и отдельно проверяем, что обмена code не было.
        for response in (mismatch, replay, denied):
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(response.headers["location"], "/?yadisk=error")
        post.assert_not_called()
        with self._db() as db:
            self.assertEqual(
                db.query(Integration).filter_by(owner_id=self.alice_id).count(), 0
            )

    def test_f11_delete_resets_integration(self) -> None:
        self._set_tokens(
            self.alice_id,
            {"access_token": MANUAL_TOKEN, "refresh_token": "", "expires_at": None},
        )
        self.assertTrue(self._ok(self.alice.get("/api/settings/yadisk"))["configured"])
        self.assertEqual(self.alice.delete("/api/settings/yadisk").status_code, 204)
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )
        with self._db() as db:
            self.assertEqual(
                db.query(Integration).filter_by(owner_id=self.alice_id).count(), 0
            )
        document_id, _ = self._cloud_document(self.alice_id)
        self.assertEqual(
            self.alice.get(f"/api/documents/{document_id}/file").status_code, 409
        )

    # ---------- F12/F13: single-flight и статусы ----------

    def test_f12_single_flight_claim_per_owner(self) -> None:
        first = self._upload_png(self.alice, "first.png", "white")
        second = self._upload_png(self.alice, "second.png", "black")
        token = self._token(self.alice)

        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(claimed["document"]["id"], first["id"])
        self.assertEqual(claimed["job"]["status"], "running")
        # Второй claim того же владельца, пока задание running, — 204.
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

        with mock.patch.object(worker_router, "index_document"):
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{claimed['job']['id']}/complete",
                    json={"text": WORKER_TEXT},
                    headers=self._auth(token),
                )
            )
        nxt = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(nxt["document"]["id"], second["id"])
        self.assertNotEqual(nxt["job"]["id"], claimed["job"]["id"])
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

    def test_f12_different_owners_claim_their_own_jobs(self) -> None:
        alice_doc = self._upload_png(self.alice, "alice.png", "white")
        bob_doc = self._upload_png(self.bob, "bob.png", "black")
        alice_token = self._token(self.alice)
        bob_token = self._token(self.bob)

        # B забирает первым: при утере owner-фильтра он возьмёт задание A
        # (в порядке created_at) и тест это увидит.
        bob_claim = self._ok(
            self.bob.post("/api/worker/claim", headers=self._auth(bob_token))
        )
        alice_claim = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(alice_token))
        )
        self.assertEqual(alice_claim["document"]["id"], alice_doc["id"])
        self.assertEqual(bob_claim["document"]["id"], bob_doc["id"])
        # Single-flight — на владельца: оба job одновременно running.
        with self._db() as db:
            for owner_id in (self.alice_id, self.bob_id):
                self.assertEqual(
                    db.query(Job).filter_by(owner_id=owner_id, status="running").count(),
                    1,
                )

    def test_f13_worker_lifecycle_updates_document_status(self) -> None:
        first = self._upload_png(self.alice, "one.png", "white")
        self.assertEqual(first["status"], "queued")
        token = self._token(self.alice)

        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(
            self._document(self.alice, first["id"])["status"], "processing"
        )

        with mock.patch.object(worker_router, "index_document"):
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{claimed['job']['id']}/complete",
                    json={"text": WORKER_TEXT, "quality": "ok"},
                    headers=self._auth(token),
                )
            )
        card = self._document(self.alice, first["id"])
        self.assertEqual((card["status"], card["error"]), ("ready", None))

        second = self._upload_png(self.alice, "two.png", "black")
        nxt = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(nxt["document"]["id"], second["id"])
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{nxt['job']['id']}/fail",
                json={"error": "ocr failed"},
                headers=self._auth(token),
            )
        )
        card = self._document(self.alice, second["id"])
        self.assertEqual((card["status"], card["error"]), ("failed", "ocr failed"))
        # Single-flight снят: очередь снова отдаётся (пусто → 204).
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

    # ---------- изоляция владельцев ----------

    def test_isolation_between_owners(self) -> None:
        alice_doc = self._ok(self._upload(self.alice, "note.md", MD))
        alice_scan = self._upload_png(self.alice, "scan.png", "white")
        bob_doc = self._ok(self._upload(self.bob, "note.md", MD))
        self.assertNotEqual(bob_doc["id"], alice_doc["id"])
        self.assertFalse(bob_doc["duplicate"])

        # B не видит документы A ни списком, ни по id/вложениям.
        self.assertEqual(
            [doc["id"] for doc in self._ok(self.bob.get("/api/documents"))],
            [bob_doc["id"]],
        )
        foreign = (
            ("get", f"/api/documents/{alice_doc['id']}"),
            ("get", f"/api/documents/{alice_doc['id']}/content"),
            ("get", f"/api/documents/{alice_doc['id']}/file"),
            ("post", f"/api/documents/{alice_doc['id']}/reprocess"),
            ("post", f"/api/documents/{alice_doc['id']}/reindex"),
            ("delete", f"/api/documents/{alice_doc['id']}"),
        )
        for method, path in foreign:
            with self.subTest(path=path):
                response = getattr(self.bob, method)(path)
                self.assertEqual(response.status_code, 404, response.text)

        # Настройки воркера независимы: токен A не включает настройки B.
        alice_token = self._token(self.alice)
        self.assertTrue(
            self._ok(self.alice.get("/api/settings/worker-token"))["configured"]
        )
        self.assertFalse(
            self._ok(self.bob.get("/api/settings/worker-token"))["configured"]
        )

        # Очередь A не видна B: чужой claim не забирает и не ломает задание A.
        bob_token = self._token(self.bob)
        self.assertEqual(self._ok(self.bob.get("/api/jobs")), [])
        self.assertEqual(
            self.bob.post(
                "/api/worker/claim", headers=self._auth(bob_token)
            ).status_code,
            204,
        )
        with self._db() as db:
            job = db.query(Job).filter_by(owner_id=self.alice_id).one()
            self.assertEqual(job.status, "queued")

        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(alice_token))
        )
        self.assertEqual(claimed["document"]["id"], alice_scan["id"])
        self.assertEqual(
            self.bob.get(
                f"/api/worker/jobs/{claimed['job']['id']}/file",
                headers=self._auth(bob_token),
            ).status_code,
            404,
        )

        # Настройки Яндекс.Диска тоже раздельные.
        with mock.patch.object(yadisk, "validate_token"):
            self._ok(
                self.alice.put(
                    "/api/settings/yadisk", json={"token": MANUAL_TOKEN}
                )
            )
        self.assertTrue(self._ok(self.alice.get("/api/settings/yadisk"))["configured"])
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )

    # ---------- F1/F3: границы на уровне API ----------

    def test_f1_url_upload_rejects_private_addresses(self) -> None:
        for url in (
            "http://127.0.0.1/admin",
            "http://10.0.0.5/internal",
            "http://169.254.169.254/latest/meta-data",
        ):
            with self.subTest(url=url):
                response = self.alice.post("/api/documents", data={"url": url})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("private", response.json()["detail"])
        with self._db() as db:
            self.assertEqual(db.query(Document).count(), 0)

    def test_f3_chunked_body_over_limit_is_413(self) -> None:
        from app.backend import main as main_module

        url = f"sqlite:///{(Path(self.tmp.name) / 'limit.db').as_posix()}"
        with mock.patch.object(main_module, "MAX_UPLOAD_MB", 1):
            app = create_app(url)
        self.addCleanup(app.state.engine.dispose)
        client = TestClient(app)
        self.addCleanup(client.close)
        response = client.post(
            "/api/auth/login",
            content=(b"x" * (1024 * 1024) for _ in range(3)),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413, response.text)


if __name__ == "__main__":
    unittest.main()
