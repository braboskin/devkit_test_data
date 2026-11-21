"""A1/A3: изоляция пользователей на маршрутах M2 (документы/задания/воркер).

Два пользователя alice/bob в одной БД. Проверяется, что чужие документы,
задания, настройки и очереди воркера недоступны ни по id, ни списками, ни
поиском, ни worker-токеном; дедуп работает только внутри владельца.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.knowledge import indexer
from app.backend.main import create_app
from app.backend.models import Job, User

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}
MARKER = "zorbulon"
DOC_MD = (
    "---\ntitle: Договор\n---\n\n"
    f"Уникальный маркер {MARKER}. Иван Петров обсудил бюджет 12.03.2026.\n"
)
OTHER_MD = (
    "---\ntitle: Смета\n---\n\n"
    "Смета проекта: материалы и работы на второй квартал.\n"
)
WORKER_TEXT = "Иван Петров обсудил бюджет проекта с ООО «Ромашка» 12.03.2026."


def make_png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


class IngestIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage_dir = Path(self.tmp.name) / "storage"

        env = mock.patch.dict(
            os.environ,
            {
                "ATLAS_EMBEDDINGS": "fake",
                "ATLAS_QDRANT_URL": ":memory:",
                "ATLAS_COLLECTION": f"test_ingest_isolation_{uuid.uuid4().hex}",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        indexer.reset_client()
        self.addCleanup(indexer.reset_client)

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

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post("/api/auth/login", json=user)
        self.assertEqual(response.status_code, 200, response.text)

    def _ok(self, response, code: int = 200) -> dict:
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _upload(
        self,
        client: TestClient,
        name: str,
        content: bytes,
        content_type: str = "text/markdown",
        **data: object,
    ):
        return client.post(
            "/api/documents",
            files={"file": (name, content, content_type)},
            data={key: str(value) for key, value in data.items()},
        )

    def _png(self, client: TestClient, color: str = "white") -> dict:
        body = self._ok(
            self._upload(client, "scan.png", make_png(color), "image/png")
        )
        self.assertEqual(body["status"], "queued")
        return body

    def _job_id(self, owner_id: str) -> int:
        with self.app.state.SessionLocal() as db:
            job = (
                db.query(Job)
                .filter_by(owner_id=owner_id)
                .order_by(Job.id.desc())
                .first()
            )
            self.assertIsNotNone(job)
            return job.id

    def _job(self, job_id: int) -> Job:
        with self.app.state.SessionLocal() as db:
            return db.get(Job, job_id)

    def _token(self, client: TestClient) -> str:
        body = self._ok(client.post("/api/settings/worker-token"), 201)
        self.assertTrue(body["token"])
        return body["token"]

    @staticmethod
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _search_ids(self, client: TestClient, query: str) -> list[int]:
        response = client.get("/api/search", params={"q": query})
        self.assertEqual(response.status_code, 200, response.text)
        return [item["document_id"] for item in response.json()]

    # ---------- документы ----------

    def test_documents_isolated_between_users(self) -> None:
        sphere = self._ok(
            self.alice.post("/api/spheres", json={"name": "Работа"}), 201
        )
        document = self._ok(
            self._upload(
                self.alice, "contract.md", DOC_MD.encode("utf-8"),
                sphere_id=sphere["id"],
            )
        )
        document_id = document["id"]

        # Списки/фильтры B: ничего чужого, чужой фильтр — 404.
        self.assertEqual(self._ok(self.bob.get("/api/documents")), [])
        for params in (
            {"q": MARKER},
            {"status": "ready"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self._ok(self.bob.get("/api/documents", params=params)), [])
        self.assertEqual(
            self.bob.get(
                "/api/documents", params={"sphere_id": sphere["id"]}
            ).status_code,
            404,
        )

        # Чужие id — 404 на чтении/файле/контенте/similar/reprocess/delete.
        for method, path in (
            ("get", f"/api/documents/{document_id}"),
            ("get", f"/api/documents/{document_id}/content"),
            ("get", f"/api/documents/{document_id}/file"),
            ("get", f"/api/documents/{document_id}/similar"),
            ("post", f"/api/documents/{document_id}/reprocess"),
            ("delete", f"/api/documents/{document_id}"),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.bob, method)(path)
                self.assertEqual(response.status_code, 404, response.text)

        # Загрузка в чужую сферу — 404.
        self.assertEqual(
            self._upload(
                self.bob, "x.md", OTHER_MD.encode("utf-8"),
                sphere_id=sphere["id"],
            ).status_code,
            404,
        )

        # Поиск B не видит документ A; A по-прежнему видит свой.
        self.assertEqual(self._search_ids(self.bob, MARKER), [])
        self.assertIn(document_id, self._search_ids(self.alice, MARKER))

        # После всех отказов документ A цел.
        self.assertEqual(
            self._ok(self.alice.get(f"/api/documents/{document_id}"))["status"],
            "ready",
        )
        self.assertIn(
            MARKER, self.alice.get(f"/api/documents/{document_id}/content").text
        )

    # ---------- задания и воркер ----------

    def test_jobs_and_worker_isolated(self) -> None:
        self._png(self.alice)
        alice_job = self._job_id(self.alice_id)

        # Списки и отмена заданий — только свои.
        self.assertEqual(self._ok(self.bob.get("/api/jobs")), [])
        self.assertEqual(
            self.bob.post(f"/api/jobs/{alice_job}/cancel").status_code, 404
        )

        alice_token = self._token(self.alice)
        bob_token = self._token(self.bob)
        # Очередь B пуста, пока у A есть задание.
        self.assertEqual(
            self.bob.post("/api/worker/claim", headers=self._auth(bob_token)).status_code,
            204,
        )
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(alice_token))
        )
        self.assertEqual(claimed["job"]["id"], alice_job)
        self.assertEqual(claimed["job"]["status"], "running")

        # Своё задание B (queued) не видно токену A.
        self._png(self.bob, "black")
        bob_job = self._job_id(self.bob_id)
        for path, payload in (
            (f"/api/worker/jobs/{bob_job}/heartbeat", None),
            (f"/api/worker/jobs/{bob_job}/complete", {"text": WORKER_TEXT}),
            (f"/api/worker/jobs/{bob_job}/fail", {"error": "x"}),
        ):
            with self.subTest(path=path):
                response = self.alice.post(
                    path, json=payload, headers=self._auth(alice_token)
                )
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(
            self.alice.get(
                f"/api/worker/jobs/{bob_job}/file",
                headers=self._auth(alice_token),
            ).status_code,
            404,
        )
        # И наоборот: токен B не трогает задание A.
        for path, payload in (
            (f"/api/worker/jobs/{alice_job}/heartbeat", None),
            (f"/api/worker/jobs/{alice_job}/complete", {"text": WORKER_TEXT}),
            (f"/api/worker/jobs/{alice_job}/fail", {"error": "x"}),
        ):
            with self.subTest(path=path):
                response = self.bob.post(
                    path, json=payload, headers=self._auth(bob_token)
                )
                self.assertEqual(response.status_code, 404, response.text)

        # Задание A и документ A не тронуты отказами B.
        self.assertEqual(self._job(alice_job).status, "running")

        # Чужая отмена — 404; своя — отмена running и документ failed.
        self.assertEqual(
            self.bob.post(f"/api/jobs/{alice_job}/cancel").status_code, 404
        )
        self.assertEqual(
            self._ok(self.alice.post(f"/api/jobs/{alice_job}/cancel"))["status"],
            "cancelled",
        )
        alice_document = self._ok(self.alice.get("/api/documents"))
        self.assertEqual([doc["status"] for doc in alice_document], ["failed"])
        self.assertEqual(
            alice_document[0]["error"], "cancelled"
        )

        # Повторная отмена — 409; worker complete отменённого — 409.
        self.assertEqual(
            self.alice.post(f"/api/jobs/{alice_job}/cancel").status_code, 409
        )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{alice_job}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(alice_token),
            ).status_code,
            409,
        )
        # Задание B осталось нетронутым.
        self.assertEqual(self._job(bob_job).status, "queued")

        # Без сессии/токена — 401.
        with TestClient(self.app) as anon:
            self.assertEqual(anon.get("/api/jobs").status_code, 401)
            self.assertEqual(
                anon.post(f"/api/jobs/{alice_job}/cancel").status_code, 401
            )
            self.assertEqual(anon.post("/api/worker/claim").status_code, 401)
            self.assertEqual(
                anon.post(
                    "/api/worker/claim", headers=self._auth("not-a-token")
                ).status_code,
                401,
            )

    # ---------- настройки и worker-токен ----------

    def test_settings_and_worker_token_isolated(self) -> None:
        previous_key = os.environ.get("ATLAS_FERNET_KEY")
        os.environ["ATLAS_FERNET_KEY"] = Fernet.generate_key().decode()

        def restore_key() -> None:
            if previous_key is None:
                os.environ.pop("ATLAS_FERNET_KEY", None)
            else:
                os.environ["ATLAS_FERNET_KEY"] = previous_key

        self.addCleanup(restore_key)

        # Worker-токен: у B пусто, токен A не открывает задания B.
        alice_token = self._token(self.alice)
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/worker-status"))["configured"],
            True,
        )
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/worker-token"))["configured"],
            False,
        )
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/worker-status"))["configured"],
            False,
        )

        # Яндекс.Диск: настройки B пусты, токен A не виден B.
        alice_secret = "y0_AgAlice-token-1234"
        self._ok(self.alice.put("/api/settings/yadisk", json={"token": alice_secret}))
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/yadisk")),
            {"configured": False, "masked": None},
        )
        self.assertNotIn(
            alice_secret, self.alice.get("/api/settings/yadisk").text
        )
        # Удаление настроек B не трогает настройки A.
        self.assertEqual(
            self.bob.delete("/api/settings/yadisk").status_code, 204
        )
        self.assertTrue(
            self._ok(self.alice.get("/api/settings/yadisk"))["configured"]
        )

        # Токен A не даёт доступа к заданию B: B сначала забирает своё.
        self._png(self.bob)
        bob_job = self._job_id(self.bob_id)
        bob_token = self._token(self.bob)
        self.assertEqual(
            self.alice.post(
                "/api/worker/claim", headers=self._auth(alice_token)
            ).status_code,
            204,
        )
        self.assertEqual(
            self._ok(
                self.bob.post(
                    "/api/worker/claim", headers=self._auth(bob_token)
                )
            )["job"]["id"],
            bob_job,
        )
        for path, payload in (
            (f"/api/worker/jobs/{bob_job}/heartbeat", None),
            (f"/api/worker/jobs/{bob_job}/complete", {"text": WORKER_TEXT}),
            (f"/api/worker/jobs/{bob_job}/fail", {"error": "x"}),
        ):
            with self.subTest(path=path):
                response = self.alice.post(
                    path, json=payload, headers=self._auth(alice_token)
                )
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(
            self.alice.get(
                f"/api/worker/jobs/{bob_job}/file",
                headers=self._auth(alice_token),
            ).status_code,
            404,
        )
        self.assertEqual(self._job(bob_job).status, "running")

    # ---------- дедуп и лимит в рамках владельца ----------

    def test_dedup_and_quota_are_owner_scoped(self) -> None:
        first = self._ok(
            self._upload(self.alice, "note.md", DOC_MD.encode("utf-8"))
        )
        second = self._ok(
            self._upload(self.alice, "copy.md", DOC_MD.encode("utf-8"))
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["id"], first["id"])

        # Тот же файл у B — свой документ, не дубль A.
        bob_doc = self._ok(
            self._upload(self.bob, "note.md", DOC_MD.encode("utf-8"))
        )
        self.assertFalse(bob_doc["duplicate"])
        self.assertNotEqual(bob_doc["id"], first["id"])
        self.assertEqual(
            [doc["id"] for doc in self._ok(self.alice.get("/api/documents"))],
            [first["id"]],
        )
        self.assertEqual(
            [doc["id"] for doc in self._ok(self.bob.get("/api/documents"))],
            [bob_doc["id"]],
        )
        self.assertIn(
            MARKER, self.bob.get(f"/api/documents/{bob_doc['id']}/content").text
        )

        # Удаление A не трогает документ B.
        self.assertEqual(
            self.alice.delete(f"/api/documents/{first['id']}").status_code, 204
        )
        self.assertEqual(
            self.bob.get(f"/api/documents/{bob_doc['id']}").status_code, 200
        )
        self.assertFalse(
            (self.storage_dir / self.alice_id / f"{first['id']}.md").exists()
        )
        self.assertTrue(
            (self.storage_dir / self.bob_id / f"{bob_doc['id']}.md").is_file()
        )

        # Лимит: превышение у A не мешает B загружать свои файлы.
        with mock.patch.object(config, "MAX_UPLOAD_BYTES", 10):
            self.assertEqual(
                self._upload(
                    self.alice, "big.md", OTHER_MD.encode("utf-8")
                ).status_code,
                413,
            )
        self.assertEqual(
            self.bob.get(f"/api/documents/{bob_doc['id']}").status_code, 200
        )
        leftovers = list(self.storage_dir.rglob("tmp-*"))
        self.assertEqual(leftovers, [])

    # ---------- негатив и повторные действия ----------

    def test_negative_and_repeat_actions(self) -> None:
        document = self._ok(
            self._upload(self.alice, "note.md", DOC_MD.encode("utf-8"))
        )
        document_id = document["id"]

        # Повторная переобработка и удаление — детерминированные коды.
        self.assertEqual(
            self.alice.post(f"/api/documents/{document_id}/reprocess").status_code,
            200,
        )
        self.assertEqual(
            self.alice.delete(f"/api/documents/{document_id}").status_code, 204
        )
        self.assertEqual(
            self.alice.delete(f"/api/documents/{document_id}").status_code, 404
        )
        self.assertEqual(
            self.alice.post(f"/api/documents/{document_id}/reprocess").status_code,
            404,
        )
        self.assertEqual(
            self.alice.get(f"/api/documents/{document_id}/similar").status_code,
            404,
        )
        self.assertEqual(
            self.alice.post("/api/jobs/999999/cancel").status_code, 404
        )

        # Невалидный вход — 422, а не 500/403.
        self.assertEqual(
            self.alice.post("/api/documents", data={}).status_code, 422
        )
        self.assertEqual(
            self.alice.post(
                "/api/documents",
                files={"file": ("note.md", b"x", "text/markdown")},
                data={"url": "http://example.com/"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self._upload(
                self.alice, "virus.exe", b"MZ", "application/octet-stream"
            ).status_code,
            422,
        )
        for params in ({}, {"q": ""}, {"q": "   "}):
            with self.subTest(params=params):
                self.assertEqual(
                    self.alice.get("/api/search", params=params).status_code, 422
                )

        # Нечисловой id — 422 (изоляция не прячет валидацию).
        self.assertEqual(
            self.alice.get("/api/documents/not-an-id").status_code, 422
        )

        # Без сессии — 401 на всех новых маршрутах, с любым телом.
        with TestClient(self.app) as anon:
            for method, path in (
                ("get", "/api/documents"),
                ("get", "/api/jobs"),
                ("get", "/api/settings/worker-token"),
                ("get", "/api/settings/yadisk"),
                ("get", f"/api/documents/{document_id}/similar"),
                ("get", "/api/search?q=x"),
                ("post", "/api/documents"),
                ("post", "/api/settings/worker-token"),
                ("post", "/api/jobs/1/cancel"),
            ):
                with self.subTest(method=method, path=path):
                    response = getattr(anon, method)(path)
                    self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(anon.post("/api/worker/claim").status_code, 401)


if __name__ == "__main__":
    unittest.main()
