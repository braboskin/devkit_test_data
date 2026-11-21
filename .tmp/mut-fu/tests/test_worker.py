"""WS-C: очередь заданий и воркер ПК — токен, claim, complete/fail, отмена."""
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Job, User, WorkerToken, utcnow
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
                json={"text": WORKER_TEXT, "attempts": claimed["job"]["attempts"]},
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
                json={"text": WORKER_TEXT, "attempts": claimed["job"]["attempts"]},
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
                json={
                    "error": "extract_failed",
                    "attempts": nxt["job"]["attempts"],
                },
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

    def test_parallel_claim_on_sqlite_keeps_one_running(self) -> None:
        """F12: два параллельных claim (2 клиента, SQLite) — один 200, один 204."""
        self._upload_png(self.alice, "p1.png", "white")
        self._upload_png(self.alice, "p2.png", "black")
        token = self._token(self.alice)
        barrier = threading.Barrier(2)
        responses: list = []
        lock = threading.Lock()

        def claim() -> None:
            barrier.wait(timeout=20)
            client = TestClient(self.app)
            try:
                response = client.post(
                    "/api/worker/claim", headers=self._auth(token)
                )
            finally:
                client.close()
            with lock:
                responses.append(response)

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertEqual(
            sorted(response.status_code for response in responses),
            [200, 204],
            [response.text for response in responses],
        )
        with self.app.state.SessionLocal() as db:
            jobs = db.query(Job).filter_by(owner_id=self.alice_id).all()
        self.assertEqual(
            sorted(job.status for job in jobs), ["queued", "running"]
        )

    def test_claim_reclaims_stale_running_job(self) -> None:
        """F12: протухший lease → задание возвращается в очередь (attempts+1)."""
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        with self.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            job.started_at = utcnow() - timedelta(
                minutes=worker_router.LEASE_MINUTES + 1
            )
            db.commit()

        reclaimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(reclaimed["job"]["id"], job_id)
        self.assertEqual(reclaimed["job"]["status"], "running")
        self.assertEqual(reclaimed["job"]["attempts"], 2)
        self.assertEqual(
            self._document(self.alice, body["id"])["status"], "processing"
        )

    def test_claim_fails_stale_job_after_max_attempts(self) -> None:
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        with self.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            job.attempts = worker_router.MAX_ATTEMPTS
            job.started_at = utcnow() - timedelta(
                minutes=worker_router.LEASE_MINUTES + 1
            )
            db.commit()

        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )
        job = self._job(job_id)
        self.assertEqual((job.status, job.error), ("failed", "worker timeout"))
        document = self._document(self.alice, body["id"])
        self.assertEqual(
            (document["status"], document["error"]), ("failed", "worker timeout")
        )

    def test_recent_running_job_is_not_reclaimed(self) -> None:
        """Свежий lease не трогаем: single-flight держит второй claim → 204."""
        self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )
        job = self._job(job_id)
        self.assertEqual((job.status, job.attempts), ("running", 1))

    def _age_lease(self, job_id: int, minutes: int | None = None) -> None:
        with self.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            job.started_at = utcnow() - timedelta(
                minutes=(worker_router.LEASE_MINUTES + 1) if minutes is None else minutes
            )
            db.commit()

    def test_old_complete_after_reclaim_is_rejected(self) -> None:
        """Lease-generation: старый воркер (attempts=1) не завершит job после reclaim."""
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self._age_lease(job_id)

        # Reclaim возвращает задание в очередь, следующий claim — attempts=2.
        reclaimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(reclaimed["job"]["id"], job_id)
        self.assertEqual(reclaimed["job"]["attempts"], 2)

        stale = self.alice.post(
            f"/api/worker/jobs/{job_id}/complete",
            json={"text": WORKER_TEXT, "attempts": 1},
            headers=self._auth(token),
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self._job(job_id).status, "running")
        self.assertEqual(
            self._document(self.alice, body["id"])["status"], "processing"
        )

        # Актуальное поколение может завершить задание.
        with mock.patch.object(worker_router, "index_document"):
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{job_id}/complete",
                    json={"text": WORKER_TEXT, "attempts": 2},
                    headers=self._auth(token),
                )
            )

    def test_reclaim_after_complete_does_not_touch_job(self) -> None:
        """Конкурентный reclaim после complete: rowcount=0, документ не сбрасывается."""
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        with mock.patch.object(worker_router, "index_document"):
            self._ok(
                self.alice.post(
                    f"/api/worker/jobs/{job_id}/complete",
                    json={"text": WORKER_TEXT, "attempts": 1},
                    headers=self._auth(token),
                )
            )
        with self.app.state.SessionLocal() as db:
            worker_router._reclaim_stale(db, self.alice_id, utcnow())
        self.assertEqual(self._job(job_id).status, "done")
        document = self._document(self.alice, body["id"])
        self.assertEqual((document["status"], document["error"]), ("ready", None))

    def test_two_reclaims_of_one_job_apply_once(self) -> None:
        body = self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self._age_lease(job_id)

        with self.app.state.SessionLocal() as db:
            worker_router._reclaim_stale(db, self.alice_id, utcnow())
        with self.app.state.SessionLocal() as db:
            worker_router._reclaim_stale(db, self.alice_id, utcnow())

        job = self._job(job_id)
        self.assertEqual((job.status, job.attempts), ("queued", 1))
        self.assertIsNone(job.started_at)
        self.assertEqual(
            self._document(self.alice, body["id"])["status"], "queued"
        )

    def test_parallel_reclaim_does_not_double_apply(self) -> None:
        """Два конкурентных claim с reclaim: job перезахвачен ровно один раз."""
        body = self._upload_png(self.alice, "stale.png", "white")
        self._upload_png(self.alice, "other.png", "black")
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self._age_lease(job_id)

        barrier = threading.Barrier(2)
        responses: list = []
        lock = threading.Lock()

        def claim() -> None:
            barrier.wait(timeout=20)
            client = TestClient(self.app)
            try:
                response = client.post(
                    "/api/worker/claim", headers=self._auth(token)
                )
            finally:
                client.close()
            with lock:
                responses.append(response)

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertEqual(
            sorted(response.status_code for response in responses),
            [200, 204],
            [response.text for response in responses],
        )
        with self.app.state.SessionLocal() as db:
            jobs = db.query(Job).filter_by(owner_id=self.alice_id).all()
        running = [job for job in jobs if job.status == "running"]
        self.assertEqual(len(running), 1)
        # reclaim не инкрементирует attempts; захват — ровно один (1 → 2).
        self.assertEqual(running[0].attempts, 2)
        self.assertEqual(
            self._document(self.alice, body["id"])["status"], "processing"
        )

    def test_heartbeat_renews_lease_and_reports_attempts(self) -> None:
        self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self._age_lease(job_id)
        old = self._job(job_id).started_at

        body = self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat",
                json={"attempts": 1},
                headers=self._auth(token),
            )
        )
        self.assertEqual(body, {"status": "running", "attempts": 1})
        self.assertGreater(self._job(job_id).started_at, old)
        # Lease продлён: claim не перезахватывает задание.
        self.assertEqual(
            self.alice.post("/api/worker/claim", headers=self._auth(token)).status_code,
            204,
        )
        self.assertEqual(self._job(job_id).attempts, 1)

    def test_heartbeat_with_stale_attempts_is_409(self) -> None:
        self._upload_png(self.alice)
        token = self._token(self.alice)
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        job_id = claimed["job"]["id"]
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat",
                json={"attempts": 99},
                headers=self._auth(token),
            ).status_code,
            409,
        )
        # Контракт lease обязателен: без attempts — 422.
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat",
                headers=self._auth(token),
            ).status_code,
            422,
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
                json={"text": "   ", "attempts": claimed["job"]["attempts"]},
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
                    "attempts": claimed["job"]["attempts"],
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
                json={"text": WORKER_TEXT, "attempts": claimed["job"]["attempts"]},
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
        claimed_second = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self._ok(
            self.alice.post(
                f"/api/worker/jobs/{second_job}/complete",
                json={
                    "text": WORKER_TEXT,
                    "quality": "needs_review",
                    "attempts": claimed_second["job"]["attempts"],
                },
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
                json={"text": WORKER_TEXT, "attempts": 1},
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
                    json={
                        "text": WORKER_TEXT,
                        "quality": "ok",
                        "attempts": claimed["job"]["attempts"],
                    },
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
                    json={
                        "text": WORKER_TEXT,
                        "quality": "ok",
                        "attempts": claimed["job"]["attempts"],
                    },
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
                json={
                    "error": "extract_failed",
                    "attempts": claimed["job"]["attempts"],
                },
                headers=self._auth(token),
            )
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "extract_failed")
        self.assertIsNotNone(failed["finished_at"])

        document = self._document(self.alice, body["id"])
        self.assertEqual(document["status"], "failed")
        self.assertEqual(document["error"], "extract_failed")

        # Повторный fail завершённого задания — 409, отмена failed — тоже.
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/fail",
                json={"error": "again", "attempts": claimed["job"]["attempts"]},
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

    def test_fail_stores_only_allowlisted_category(self) -> None:
        """F8: произвольный текст воркера (путь/URL/секрет) в БД не попадает."""
        leak = (
            f"OSError: {self.storage_dir}/scan.png "
            "https://example.com/x?token=SECRET_TOKEN"
        )
        cases = (
            ("extract_failed", leak),
            ("unsupported_format", "unsupported_format"),
            ("too_large", "too_large"),
            ("timeout", "timeout"),
            ("cancelled", "cancelled"),
            ("extract_failed", ""),
        )
        token = self._token(self.alice)
        colors = ("white", "black", "red", "blue", "green", "yellow")
        for (expected, payload), color in zip(cases, colors):
            with self.subTest(payload=payload):
                body = self._upload_png(self.alice, f"fail-{color}.png", color)
                claimed = self._ok(
                    self.alice.post("/api/worker/claim", headers=self._auth(token))
                )
                failed = self._ok(
                    self.alice.post(
                        f"/api/worker/jobs/{claimed['job']['id']}/fail",
                        json={
                            "error": payload,
                            "attempts": claimed["job"]["attempts"],
                        },
                        headers=self._auth(token),
                    )
                )
                self.assertEqual(failed["error"], expected)
                document = self._document(self.alice, body["id"])
                self.assertEqual(document["status"], "failed")
                self.assertEqual(document["error"], expected)
                for fragment in (
                    str(self.storage_dir), "https://", "SECRET_TOKEN", "OSError",
                ):
                    self.assertNotIn(fragment, document["error"])

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
                json={"text": WORKER_TEXT, "attempts": 1},
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
                json={"text": WORKER_TEXT, "attempts": 1},
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
                    f"/api/worker/jobs/{job_id}/heartbeat",
                    json={"attempts": claimed["job"]["attempts"]},
                    headers=self._auth(token),
                )
            ),
            {"status": "running", "attempts": claimed["job"]["attempts"]},
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
                    {"error": "x", "attempts": 1}
                    if path.endswith("/fail")
                    else {"text": WORKER_TEXT, "attempts": 1}
                    if path.endswith("/complete")
                    else {"attempts": 1}
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
                json={"text": WORKER_TEXT, "attempts": claimed["job"]["attempts"]},
                headers=self._auth(token),
            )
        )
        self.assertEqual(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/heartbeat",
                json={"attempts": claimed["job"]["attempts"]},
                headers=self._auth(token),
            ).status_code,
            409,
        )
        self.assertEqual(
            self.alice.post(
                "/api/worker/jobs/999999/heartbeat",
                json={"attempts": 1},
                headers=self._auth(token),
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
            (
                f"/api/worker/jobs/{job_id}/complete",
                {"text": WORKER_TEXT, "attempts": claimed["job"]["attempts"]},
            ),
            (
                f"/api/worker/jobs/{job_id}/fail",
                {"error": "x", "attempts": claimed["job"]["attempts"]},
            ),
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
                json={"attempts": claimed["job"]["attempts"]},
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

    def test_worker_script_sends_failure_category_only(self) -> None:
        """F8 на стороне воркера: в API уходит категория, не текст ошибки."""
        import importlib.util

        import httpx

        spec = importlib.util.spec_from_file_location(
            "atlas_worker_script", ROOT / "scripts" / "worker.py"
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)

        self.assertEqual(
            script.failure_category(RuntimeError("path /secret")),
            "extract_failed",
        )
        self.assertEqual(
            script.failure_category(httpx.TimeoutException("slow")), "timeout"
        )

        sent: dict = {}

        class _Client:
            def post(self, url, json):
                sent.update(url=url, json=json)

        script._fail(
            _Client(),
            7,
            2,
            script.failure_category(
                OSError("https://example.com/x?token=SECRET_TOKEN")
            ),
        )
        self.assertEqual(sent["url"], "/api/worker/jobs/7/fail")
        self.assertEqual(
            sent["json"], {"error": "extract_failed", "attempts": 2}
        )
        self.assertNotIn("SECRET_TOKEN", str(sent))


if __name__ == "__main__":
    unittest.main()
