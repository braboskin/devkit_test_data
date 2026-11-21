"""WS-B2: F12 — single-flight claim на PostgreSQL (временный кластер).

Без `initdb`/`pg_ctl` в PATH (или `PG_BIN`) тесты скипаются, как в `test_migrations`.
"""
from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.backend.auth import hash_password, hash_token
from app.backend.main import create_app
from app.backend.models import Document, Job, User, WorkerToken, utcnow
from app.backend.routers.worker import LEASE_MINUTES
from tests.test_migrations import find_pg_bin, free_port, remove_tree, upgrade


class PostgresClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        binaries = find_pg_bin()
        if binaries is None:
            raise unittest.SkipTest(
                "PostgreSQL не найден: задайте PG_BIN (initdb.exe и pg_ctl.exe)"
            )
        cls.initdb, cls.pg_ctl = binaries
        cls.tmp = Path(tempfile.mkdtemp(prefix="atlas-pg-claim-"))
        cls.data = cls.tmp / "data"
        cls.log = cls.tmp / "postgres.log"
        cls.pg_ctl_log = cls.tmp / "pg_ctl.log"
        port = free_port()
        try:
            result = subprocess.run(
                [
                    str(cls.initdb),
                    "-D",
                    str(cls.data),
                    "-U",
                    "postgres",
                    "-A",
                    "trust",
                    "-E",
                    "UTF8",
                    "--no-locale",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise unittest.SkipTest(
                    "initdb недоступен: " + result.stdout + result.stderr
                )
            # stdout/stderr — в файлы, не в pipe: демон их наследует.
            with cls.pg_ctl_log.open("w") as out:
                started = subprocess.run(
                    [
                        str(cls.pg_ctl),
                        "start",
                        "-D",
                        str(cls.data),
                        "-l",
                        str(cls.log),
                        "-o",
                        f"-p {port} -c listen_addresses=127.0.0.1",
                        "-w",
                        "-t",
                        "60",
                    ],
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                )
            if started.returncode != 0:
                raise unittest.SkipTest(
                    "pg_ctl start не удался: "
                    + cls.pg_ctl_log.read_text(errors="replace")
                )
            base = f"postgresql+psycopg://postgres@127.0.0.1:{port}"
            admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
            try:
                with admin.connect() as conn:
                    conn.execute(text("CREATE DATABASE atlas"))
            finally:
                admin.dispose()
            cls.url = f"{base}/atlas"
            upgrade(cls.url)
            cls.app = create_app(cls.url)
        except BaseException:
            cls._shutdown()
            raise

    @classmethod
    def _shutdown(cls) -> None:
        if (cls.data / "postmaster.pid").exists():
            subprocess.run(
                [
                    str(cls.pg_ctl),
                    "stop",
                    "-D",
                    str(cls.data),
                    "-m",
                    "immediate",
                    "-w",
                    "-t",
                    "60",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
        remove_tree(cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.state.engine.dispose()
        cls._shutdown()

    def setUp(self) -> None:
        self._clear()

    # ---------- helpers ----------

    def _clear(self) -> None:
        with self.app.state.SessionLocal() as db:
            db.query(Job).delete()
            db.query(Document).delete()
            db.query(WorkerToken).delete()
            db.query(User).delete()
            db.commit()

    def _user(self, name: str) -> tuple[str, str]:
        token = f"token-{name}"
        with self.app.state.SessionLocal() as db:
            user = User(
                username=name, password_hash=hash_password(f"{name}-pass")
            )
            db.add(user)
            db.flush()
            db.add(
                WorkerToken(owner_id=user.id, token_hash=hash_token(token))
            )
            db.commit()
            return user.id, token

    def _add_job(self, db, owner_id: str, status: str = "queued") -> Job:
        document = Document(
            owner_id=owner_id,
            title=f"doc-{status}",
            source_type="file",
            size_bytes=0,
            storage="none",
            status="processing" if status == "running" else "queued",
            tags=[],
            entities={},
        )
        db.add(document)
        db.flush()
        job = Job(
            owner_id=owner_id,
            type="ocr",
            status=status,
            payload={"document_id": document.id, "kind": "ocr"},
        )
        db.add(job)
        db.flush()
        return job

    def _seed(self, owner_id: str, count: int) -> None:
        with self.app.state.SessionLocal() as db:
            for _ in range(count):
                self._add_job(db, owner_id)
            db.commit()

    def _claim(self, token: str):
        client = TestClient(self.app)
        try:
            return client.post(
                "/api/worker/claim",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            client.close()

    def _claim_together(self, tokens: list[str]) -> list:
        barrier = threading.Barrier(len(tokens))
        responses: list = []
        lock = threading.Lock()

        def claim(token: str) -> None:
            barrier.wait(timeout=20)
            response = self._claim(token)
            with lock:
                responses.append(response)

        threads = [
            threading.Thread(target=claim, args=(token,)) for token in tokens
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertEqual(len(responses), len(tokens))
        return responses

    def _counts(self, owner_id: str) -> dict[str, int]:
        with self.app.state.SessionLocal() as db:
            return {
                status: db.query(Job)
                .filter_by(owner_id=owner_id, status=status)
                .count()
                for status in ("queued", "running", "done", "failed")
            }

    # ---------- тесты ----------

    def test_migration_creates_partial_unique_index(self) -> None:
        engine = create_engine(self.url)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE indexname = 'uq_jobs_owner_running'"
                    )
                ).first()
        finally:
            engine.dispose()
        self.assertIsNotNone(row)
        self.assertIn("unique", row[0].lower())
        self.assertIn("running", row[0].lower())

    def test_index_blocks_second_running_job(self) -> None:
        owner_id, _ = self._user("alice")
        with self.app.state.SessionLocal() as db:
            self._add_job(db, owner_id, "running")
            db.commit()
            with self.assertRaises(IntegrityError):
                self._add_job(db, owner_id, "running")
                db.commit()
            db.rollback()
        self.assertEqual(self._counts(owner_id)["running"], 1)

    def test_different_owners_claim_in_parallel(self) -> None:
        alice, alice_token = self._user("alice")
        bob, bob_token = self._user("bob")
        self._seed(alice, 1)
        self._seed(bob, 1)

        responses = self._claim_together([alice_token, bob_token])
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertNotEqual(
            responses[0].json()["job"]["id"], responses[1].json()["job"]["id"]
        )
        self.assertEqual(self._counts(alice)["running"], 1)
        self.assertEqual(self._counts(bob)["running"], 1)

    def test_same_owner_parallel_claim_keeps_one_running(self) -> None:
        for _ in range(3):
            with self.subTest(owner="alice"):
                self._clear()
                owner, token = self._user("alice")
                self._seed(owner, 2)
                responses = self._claim_together([token, token])
                self.assertEqual(
                    sorted(r.status_code for r in responses),
                    [200, 204],
                    [r.text for r in responses],
                )
                counts = self._counts(owner)
                self.assertEqual(counts["running"], 1, counts)
                self.assertEqual(counts["queued"], 1, counts)
                winner = next(r for r in responses if r.status_code == 200)
                # Lease-generation виден воркеру в ответе claim.
                self.assertEqual(winner.json()["job"]["attempts"], 1)

    def test_parallel_claim_reclaims_stale_lease_once(self) -> None:
        """Два конкурентных claim с reclaim: протухший job перехвачен ровно раз."""
        owner, token = self._user("alice")
        self._seed(owner, 2)
        first = self._claim(token)
        self.assertEqual(first.status_code, 200, first.text)
        job_id = first.json()["job"]["id"]
        with self.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            job.started_at = utcnow() - timedelta(
                minutes=LEASE_MINUTES + 1
            )
            db.commit()

        responses = self._claim_together([token, token])
        self.assertEqual(
            sorted(r.status_code for r in responses),
            [200, 204],
            [r.text for r in responses],
        )
        with self.app.state.SessionLocal() as db:
            running = (
                db.query(Job)
                .filter_by(owner_id=owner, status="running")
                .all()
            )
        self.assertEqual(len(running), 1)
        # reclaim не инкрементирует attempts; захват — ровно один (1 → 2).
        self.assertEqual(running[0].attempts, 2)
        self.assertEqual(self._counts(owner)["queued"], 1)


if __name__ == "__main__":
    unittest.main()
