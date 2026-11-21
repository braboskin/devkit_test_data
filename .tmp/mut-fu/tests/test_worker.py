"""WS-C: очередь заданий и воркер ПК — токен, claim, complete/fail, отмена."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Job, User, WorkerToken
from app.backend.routers import documents, worker as worker_router

ROOT = Path(__file__).resolve().parents[1]
ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}
WORKER_TEXT = (
    "Иван Петров обсудил бюджет проекта с ООО «Ромашка» 12.03.2026. #финансы"
)
JOB_FIELDS = {
    "id",
    "type",
    "status",
    "payload",
    "attempts",
    "created_at",
    "started_at",
    "finished_at",
    "error",
}


def make_png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


class WorkerTests(unittest.TestCase):
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

        # Хранилище — временный каталог (в тестах не трогаем `data/storage`).
        patcher = mock.patch.object(config, "STORAGE_DIR", self.storage_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def _token(self, client: TestClient) -> str:
        body = self._ok(client.post("/api/settings/worker-token"), 201)
        self.assertTrue(body["token"])
        return body["token"]

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _upload_png(
        self,
        client: TestClient,
        name: str = "scan.png",
        color: str = "white",
        storage: str = "local",
    ) -> dict:
        content = make_png(color)
        response = client.post(
            "/api/documents", files={"file": (name, content, "image/png")}
        )
        body = self._ok(response)
        self.assertFalse(body["duplicate"])
        self.png = content
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["storage"], storage)
        return body

    def _job_id(self, owner_id: str) -> int:
        with self.app.state.SessionLocal() as db:
            return (
                db.query(Job)
                .filter_by(owner_id=owner_id)
                .order_by(Job.id.desc())
                .first()
                .id
            )

    def _job(self, job_id: int) -> Job:
        with self.app.state.SessionLocal() as db:
            return db.get(Job, job_id)

    def _document(self, client: TestClient, document_id: int) -> dict:
        return self._ok(client.get(f"/api/documents/{document_id}"))

    # ---------- 1. настройки воркер-токена ----------

    def test_worker_token_settings(self) -> None:
        body = self._ok(self.alice.get("/api/settings/worker-token"))
        self.assertEqual(
            body,
            {"configured": False, "created_at": None, "last_seen_at": None},
        )

        token = self._token(self.alice)
        self.assertGreaterEqual(len(token), 32)
        listed = self._ok(self.alice.get("/api/settings/worker-token"))
        self.assertTrue(listed["configured"])
        self.assertIsNotNone(listed["created_at"])
        self.assertNotIn("token", listed)
        self.assertNotIn(token, str(listed))
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/worker-status")),
            {"configured": True, "last_seen_at": None},
        )
        # В БД только sha256.
        with self.app.state.SessionLocal() as db:
            stored = db.query(WorkerToken).one()
            self.assertNotEqual(stored.token_hash, token)
            self.assertEqual(len(stored.token_hash), 64)

        # Чужой владелец не видит токен и его статус.
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/worker-token")),
            {"configured": False, "created_at": None, "last_seen_at": None},
        )
        self.assertEqual(
            self._ok(self.bob.get("/api/settings/worker-status")),
            {"configured": False, "last_seen_at": None},
        )

        # Повторная выдача заменяет прежний токен.
        new_token = self._token(self.alice)
        self.assertNotEqual(new_token, token)
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            401,
        )

        # DELETE отзывает токен.
        self.assertEqual(
            self.alice.delete("/api/settings/worker-token").status_code, 204
        )
        self.assertEqual(
            self._ok(self.alice.get("/api/settings/worker-status")),
            {"configured": False, "last_seen_at": None},
        )
        self.assertEqual(
            self.alice.post(
                "/api/worker/claim", headers=self._auth(new_token)
            ).status_code,
            401,
        )

    # ---------- 2. claim ----------

    def test_claim_takes_next_job_and_empty_queue(self) -> None:
        first = self._upload_png(self.alice, "one.png", "white")
        second = self._upload_png(self.alice, "two.png", "black")
        token = self._token(self.alice)

        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(claimed["job"]["status"], "running")
        self.assertEqual(claimed["job"]["attempts"], 1)
        self.assertIsNotNone(claimed["job"]["started_at"])
        self.assertEqual(
            claimed["job"]["payload"]["document_id"], first["id"]
        )
        self.assertEqual(
            claimed["document"],
            {
                "id": first["id"],
                "title": "one",
                "mime": "image/png",
                "storage": "local",
                "storage_ref": first["storage_ref"],
            },
        )

        # Single-flight: пока первое задание `running`, второе не берётся.
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )
        self.assertEqual(
            len(self._ok(self.alice.get("/api/jobs", params={"status": "running"}))),
            1,
        )

        # Удалённый оригинал не скачивается (409: из облака не тянем).
        (self.storage_dir / first["storage_ref"]).unlink()
        self.assertEqual(
            self.alice.get(
                f"/api/worker/jobs/{claimed['job']['id']}/file",
                headers=self._auth(token),
            ).status_code,
            409,
        )

        # После завершения первого — очередь отдаёт следующее задание.
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
        self.assertNotEqual(nxt["job"]["id"], claimed["job"]["id"])
        self.assertEqual(nxt["job"]["payload"]["document_id"], second["id"])
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

        # Без Bearer (в т.ч. с cookie-сессией) и с мусорным токеном — 401.
        self.assertEqual(self.alice.post("/api/worker/claim").status_code, 401)
        self.assertEqual(
            self.alice.post(
                "/api/worker/claim", headers=self._auth("not-a-token")
            ).status_code,
            401,
        )

        jobs = self._ok(self.alice.get("/api/jobs", params={"status": "running"}))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(set(jobs[0]), JOB_FIELDS)
        self.assertEqual([job["status"] for job in jobs], ["running"])
        self.assertEqual(
            [job["id"] for job in self._ok(self.alice.get("/api/jobs", params={"status": "done"}))],
            [claimed["job"]["id"]],
        )

    def test_single_flight_and_document_statuses(self) -> None:
        """F12/F13: один running job на владельца; claim → `processing`."""
        first = self._upload_png(self.alice, "first.png", "white")
        second = self._upload_png(self.alice, "second.png", "black")
        token = self._token(self.alice)

        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self.assertEqual(
            self._document(self.alice, first["id"])["status"], "processing"
        )
        # Второй claim того же владельца — 204, пока задание `running`.
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )
        self.assertEqual(
            [job["id"] for job in
             self._ok(self.alice.get("/api/jobs", params={"status": "running"}))],
            [job_id],
        )

        # complete → ready и single-flight снимается.
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(token),
            )
        )
        self.assertEqual(
            self._document(self.alice, first["id"])["status"], "ready"
        )
        nxt = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(nxt["job"]["payload"]["document_id"], second["id"])
        self.assertEqual(
            self._document(self.alice, second["id"])["status"], "processing"
        )

        # fail → failed и очередь снова доступна для третьего задания.
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{nxt['job']['id']}/fail",
                json={"error": "extract failed"},
                headers=self._auth(token),
            )
        )
        self.assertEqual(
            self._document(self.alice, second["id"])["status"], "failed"
        )
        third = self._upload_png(self.alice, "third.png", "blue")
        last = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(last["job"]["payload"]["document_id"], third["id"])
        self.assertEqual(
            self._document(self.alice, third["id"])["status"], "processing"
        )

    def test_claim_race_on_unique_index_returns_204(self) -> None:
        """Гонка на PG: partial unique index отбил второй running-job → 204."""
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session as SASession

        body = self._upload_png(self.alice, "race.png", "white")
        token = self._token(self.alice)
        real_commit = SASession.commit
        calls = {"n": 0}

        def commit(session):
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("UPDATE jobs", {}, Exception("duplicate"))
            return real_commit(session)

        with mock.patch.object(SASession, "commit", commit):
            response = self.alice.post(
                "/api/worker/claim", headers=self._auth(token)
            )
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self._job(self._job_id(self.alice_id)).status, "queued")
        self.assertEqual(
            self._document(self.alice, body["id"])["status"], "queued"
        )

    # ---------- 3. complete ----------

    # Индексация без модели/Qdrant: в тестах `index_document` — мок (F9).
    @mock.patch.object(worker_router, "index_document")
    def test_complete_fills_document_and_chunks(self, index_document) -> None:
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]

        original = self.alice.get(
            f"/api/worker/jobs/{job_id}/file", headers=self._auth(token)
        )
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.content, self.png)

        # Пустой текст не принимается, задание остаётся `running`.
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": "   "},
                headers=self._auth(token),
            ).status_code,
            422,
        )
        self.assertEqual(self._job(job_id).status, "running")

        done = self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={
                    "text": WORKER_TEXT,
                    "pages": 1,
                    "engine": "tesseract",
                    "quality": "ok",
                },
                headers=self._auth(token),
            )
        )
        self.assertEqual(done["status"], "done")
        self.assertIsNotNone(done["finished_at"])

        document = self._document(self.alice, body["id"])
        self.assertEqual(document["status"], "ready")
        self.assertEqual(document["pages"], 1)
        self.assertTrue(document["annotation"])
        self.assertTrue(document["doc_class"])
        self.assertIn("финансы", document["tags"])
        self.assertIn("Иван Петров", document["entities"]["people"])
        self.assertIsNone(document["error"])

        content = self.alice.get(f"/api/documents/{body['id']}/content")
        self.assertEqual(content.status_code, 200)
        self.assertIn("Иван Петров", content.text)
        with self.app.state.SessionLocal() as db:
            chunks = (
                db.query(Chunk)
                .filter_by(document_id=body["id"])
                .order_by(Chunk.ord)
                .all()
            )
            self.assertTrue(chunks)
            self.assertEqual(chunks[0].owner_id, self.alice_id)
            self.assertIn("Иван Петров", " ".join(chunk.text for chunk in chunks))
            self.assertTrue(all(chunk.tokens > 0 for chunk in chunks))

        # Повторный complete завершённого задания — 409, отмена done — тоже.
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(token),
            ).status_code,
            409,
        )
        self.assertEqual(
            self.alice.post(f"/api/jobs/{job_id}/cancel").status_code, 409
        )
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

        # quality != ok → документ на проверку.
        second = self._upload_png(self.alice, "review.png", "red")
        second_job = self._job_id(self.alice_id)
        self._ok(self.alice.post("/api/worker/claim", headers=self._auth(token)))
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{second_job}/complete",
                json={"text": WORKER_TEXT, "quality": "needs_review"},
                headers=self._auth(token),
            )
        )
        self.assertEqual(
            self._document(self.alice, second["id"])["status"], "needs_review"
        )

        # Чужое задание — 404.
        bob_token = self._token(self.bob)
        self.assertEqual(
            self.bob.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(bob_token),
            ).status_code,
            404,
        )
        # Индексация вызвана для обоих завершённых заданий.
        self.assertEqual(index_document.call_count, 2)

    def test_index_failure_is_visible_in_document_error(self) -> None:
        """F9: сбой индексации у воркера виден в `document.error`, ответ жив."""
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        with mock.patch.object(
            worker_router,
            "index_document",
            side_effect=RuntimeError("qdrant is down"),
        ):
            done = self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{job_id}/complete",
                    json={"text": WORKER_TEXT, "quality": "ok"},
                    headers=self._auth(token),
                )
            )
        self.assertEqual(done["status"], "done")
        document = self._document(self.alice, body["id"])
        self.assertEqual(document["status"], "ready")
        self.assertEqual(document["error"], "indexing failed")

    def test_index_success_keeps_document_error_empty(self) -> None:
        body = self._upload_png(self.alice, "indexed.png", "black")
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        with mock.patch.object(worker_router, "index_document") as index:
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{job_id}/complete",
                    json={"text": WORKER_TEXT, "quality": "ok"},
                    headers=self._auth(token),
                )
            )
        index.assert_called_once()
        document = self._document(self.alice, body["id"])
        self.assertEqual(document["status"], "ready")
        self.assertIsNone(document["error"])

    # ---------- 4. fail ----------

    def test_fail_marks_job_and_document(self) -> None:
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]

        failed = self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/fail",
                json={"error": "x" * 600},
                headers=self._auth(token),
            )
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(failed["error"]), 500)
        self.assertIsNotNone(failed["finished_at"])

        document = self._document(self.alice, body["id"])
        self.assertEqual(document["status"], "failed")
        self.assertEqual(document["error"], "x" * 500)

        # Повторный fail завершённого задания — 409, отмена failed — тоже.
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/fail",
                json={"error": "again"},
                headers=self._auth(token),
            ).status_code,
            409,
        )
        self.assertEqual(
            self.alice.post(f"/api/jobs/{job_id}/cancel").status_code, 409
        )
        self.assertEqual(
            self._ok(self.alice.get("/api/jobs", params={"status": "failed"}))[0][
                "id"
            ],
            job_id,
        )

    # ---------- 5. отмена ----------

    def test_cancel_queued_and_running(self) -> None:
        queued = self._upload_png(self.alice, "queued.png", "white")
        queued_job = self._job_id(self.alice_id)
        cancelled = self._ok(self.alice.post(f"/api/jobs/{queued_job}/cancel"))
        self.assertEqual(cancelled["status"], "cancelled")
        document = self._document(self.alice, queued["id"])
        self.assertEqual(document["status"], "failed")
        self.assertEqual(document["error"], "cancelled")

        # Повторная отмена и завершение отменённого задания — 409.
        self.assertEqual(
            self.alice.post(f"/api/jobs/{queued_job}/cancel").status_code, 409
        )
        token = self._token(self.alice)
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{queued_job}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(token),
            ).status_code,
            409,
        )
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )

        # Отмена running: воркер получает 409 на complete.
        running = self._upload_png(self.alice, "running.png", "black")
        running_job = self._job_id(self.alice_id)
        self._ok(self.alice.post("/api/worker/claim", headers=self._auth(token)))
        self.assertEqual(self._job(running_job).status, "running")
        self.assertEqual(
            self._ok(self.alice.post(f"/api/jobs/{running_job}/cancel"))["status"],
            "cancelled",
        )
        self.assertEqual(
            self._document(self.alice, running["id"])["status"], "failed"
        )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{running_job}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(token),
            ).status_code,
            409,
        )

        # Чужое задание — 404 даже для владельца другого токена.
        self._upload_png(self.bob, "bob.png")
        bob_job = self._job_id(self.bob_id)
        self.assertEqual(
            self.alice.post(f"/api/jobs/{bob_job}/cancel").status_code, 404
        )

        # Без сессии — 401.
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.get("/api/jobs").status_code, 401)
            self.assertEqual(
                anonymous.post(f"/api/jobs/{bob_job}/cancel").status_code, 401
            )

    # ---------- 6. heartbeat ----------

    def test_heartbeat_and_foreign_jobs(self) -> None:
        self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]

        self.assertEqual(
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{job_id}/heartbeat", headers=self._auth(token)
                )
            ),
            {"status": "running"},
        )
        self.assertIsNotNone(
            self._ok(self.alice.get("/api/settings/worker-status"))["last_seen_at"]
        )

        # Чужой токен не видит задание; cookie-сессия не подходит для воркера.
        bob_token = self._token(self.bob)
        for path in (
            f"/api/worker/jobs/{job_id}/heartbeat",
            f"/api/worker/jobs/{job_id}/complete",
            f"/api/worker/jobs/{job_id}/fail",
        ):
            with self.subTest(path=path):
                payload = (
                    {"error": "x"}
                    if path.endswith("/fail")
                    else {"text": WORKER_TEXT}
                )
                response = self.bob.post(
                    path, json=payload, headers=self._auth(bob_token)
                )
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(
            self.bob.get(
                f"/api/worker/jobs/{job_id}/file", headers=self._auth(bob_token)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.alice.get(f"/api/worker/jobs/{job_id}/file").status_code, 401
        )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.alice.post("/api/worker/jobs/999999/heartbeat").status_code, 401
        )

        # Завершённое задание: heartbeat → 409, несуществующее → 404.
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": WORKER_TEXT},
                headers=self._auth(token),
            )
        )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat", headers=self._auth(token)
            ).status_code,
            409,
        )
        self.assertEqual(
            self.alice.post(
                "/api/worker/jobs/999999/heartbeat", headers=self._auth(token)
            ).status_code,
            404,
        )

    # ---------- 7. изоляция владельцев ----------

    def test_owner_isolation(self) -> None:
        alice_token = self._token(self.alice)
        bob_token = self._token(self.bob)

        body = self._upload_png(self.bob, "bob.png")
        # Очередь A пуста, даже когда у B есть задание.
        self.assertEqual(
            self.alice.post(
                "/api/worker/claim", headers=self._auth(alice_token)
            ).status_code,
            204,
        )
        self.assertEqual(self._ok(self.alice.get("/api/jobs")), [])
        claimed = self._ok(
            self.bob.post("/api/worker/claim", headers=self._auth(bob_token))
        )
        self.assertEqual(claimed["document"]["id"], body["id"])
        job_id = claimed["job"]["id"]

        # Токен A не даёт доступа к заданиям B.
        self.assertEqual(
            self.alice.get(
                f"/api/worker/jobs/{job_id}/file", headers=self._auth(alice_token)
            ).status_code,
            404,
        )
        for path, payload in (
            (f"/api/worker/jobs/{job_id}/complete", {"text": WORKER_TEXT}),
            (f"/api/worker/jobs/{job_id}/fail", {"error": "x"}),
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.alice.post(
                        path, json=payload, headers=self._auth(alice_token)
                    ).status_code,
                    404,
                )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat",
                headers=self._auth(alice_token),
            ).status_code,
            404,
        )

        # Задание B осталось running, документ взят в обработку (F13).
        self.assertEqual(self._job(job_id).status, "running")
        self.assertEqual(
            self._document(self.bob, body["id"])["status"], "processing"
        )

        # Cookie-сессия B не авторизует воркер-запросы.
        for path in (
            f"/api/worker/jobs/{job_id}/file",
        ):
            self.assertEqual(self.bob.get(path).status_code, 401)
        for path, payload in (
            (f"/api/worker/jobs/{job_id}/complete", {"text": WORKER_TEXT}),
            (f"/api/worker/jobs/{job_id}/fail", {"error": "x"}),
        ):
            self.assertEqual(
                self.bob.post(path, json=payload).status_code, 401
            )
        self.assertEqual(
            self.bob.post(f"/api/worker/jobs/{job_id}/heartbeat").status_code, 401
        )

        # Список заданий и отмена — только свои.
        self.assertEqual(
            [job["id"] for job in self._ok(self.bob.get("/api/jobs"))], [job_id]
        )
        self.assertEqual(
            [job["id"] for job in self._ok(self.alice.get("/api/jobs"))], []
        )
        self.assertEqual(
            self.alice.post(f"/api/jobs/{job_id}/cancel").status_code, 404
        )

    # ---------- 8. yandex-оригинал: отдаём локальную копию ----------

    def test_file_serves_local_copy_of_yandex_original(self) -> None:
        with (
            mock.patch.object(documents, "YADISK_THRESHOLD", 10),
            mock.patch.object(yadisk, "_token_for", return_value="token"),
            # Папки и выгрузка — без сети: проверяем только переход на `yandex`.
            mock.patch.object(yadisk, "ensure_folder"),
            mock.patch.object(yadisk, "upload_file") as upload,
        ):
            body = self._upload_png(
                self.alice, "remote.png", "blue", storage="yandex"
            )
        upload.assert_called_once()
        self.assertEqual(body["storage"], "yandex")
        remote = f"/atlas/{self.alice_id}/{body['id']}.png"
        self.assertEqual(body["storage_ref"], f"disk:{remote}")
        local = self.storage_dir / self.alice_id / f"{body['id']}.png"
        self.assertTrue(local.is_file())
        self.assertEqual(upload.call_args.args, ("token", remote, local))

        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self.assertEqual(claimed["document"]["storage"], "yandex")

        response = self.alice.get(
            f"/api/worker/jobs/{job_id}/file", headers=self._auth(token)
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, self.png)

        # Токена Яндекса нет — скачать нечем: 409, а не 404/500.
        local.unlink()
        missing = self.alice.get(
            f"/api/worker/jobs/{job_id}/file", headers=self._auth(token)
        )
        self.assertEqual(missing.status_code, 409, missing.text)
        self.assertIn("not stored locally", missing.json()["detail"])

    def test_file_downloads_cloud_original(self) -> None:
        """F4: локальной копии нет — воркер получает оригинал из Яндекса."""
        with (
            mock.patch.object(documents, "YADISK_THRESHOLD", 10),
            mock.patch.object(yadisk, "_token_for", return_value="token"),
            mock.patch.object(yadisk, "ensure_folder"),
            mock.patch.object(yadisk, "upload_file"),
        ):
            body = self._upload_png(
                self.alice, "cloud.png", "blue", storage="yandex"
            )
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        local = self.storage_dir / self.alice_id / f"{body['id']}.png"
        local.unlink()

        downloaded: list[tuple[str, str, Path]] = []

        def download_file(token_, remote, dest):
            downloaded.append((token_, remote, Path(dest)))
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(self.png)

        with (
            mock.patch.object(yadisk, "_token_for", return_value="token"),
            mock.patch.object(
                yadisk, "download_file", side_effect=download_file
            ) as download,
        ):
            response = self.alice.get(
                f"/api/worker/jobs/{job_id}/file", headers=self._auth(token)
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, self.png)
        self.assertTrue(local.is_file())
        download.assert_called_once()
        self.assertEqual(
            downloaded[0][1], f"/atlas/{self.alice_id}/{body['id']}.png"
        )

    # ---------- 9. CLI воркера ----------

    def test_worker_script_compiles_and_has_help(self) -> None:
        script = ROOT / "scripts" / "worker.py"
        source = script.read_text(encoding="utf-8")
        compile(source, str(script), "exec")

        env = {
            **os.environ,
            "ATLAS_BASE_URL": "http://127.0.0.1:9",
            "ATLAS_WORKER_TOKEN": "dummy",
        }
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--once", result.stdout)
        self.assertIn("--interval", result.stdout)
        self.assertIn("--concurrency", result.stdout)


if __name__ == "__main__":
    unittest.main()
