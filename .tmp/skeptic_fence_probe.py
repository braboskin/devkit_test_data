"""Probe: in-flight old complete is fenced by the atomic UPDATE."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path.cwd()))

from tests.test_worker_pg import PostgresClaimTests  # noqa: E402
from app.backend.models import Chunk, Document, Job, utcnow  # noqa: E402
from app.backend.routers import worker as worker_router  # noqa: E402


def main() -> None:
    PostgresClaimTests.setUpClass()
    try:
        cls = PostgresClaimTests
        inst = PostgresClaimTests("runTest")
        inst._clear()
        owner, token = inst._user("alice")
        inst._seed(owner, 1)
        first = inst._claim(token).json()["job"]
        job_id = first["id"]
        assert first["attempts"] == 1
        with cls.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            document_id = job.payload["document_id"]
            job.started_at = utcnow() - timedelta(
                minutes=worker_router.LEASE_MINUTES + 1
            )
            db.commit()
        with cls.app.state.SessionLocal() as db:
            token_row = db.query(__import__("app.backend.models", fromlist=["WorkerToken"]).WorkerToken).filter_by(owner_id=owner).one()
            worker_router.claim(db=db, token=token_row)
        with cls.app.state.SessionLocal() as db:
            print("after_new_claim", db.get(Job, job_id).status, db.get(Job, job_id).attempts)

        def read_job(db, _token, _job_id, _attempts):
            # in-flight: _running_job already passed before reclaim/new claim
            return db.get(Job, job_id)

        with mock.patch.object(worker_router, "_running_job", side_effect=read_job):
            from fastapi.testclient import TestClient

            client = TestClient(cls.app)
            try:
                response = client.post(
                    f"/api/worker/jobs/{job_id}/complete",
                    json={"text": "old result", "attempts": 1},
                    headers={"Authorization": f"Bearer {token}"},
                )
            finally:
                client.close()
        print("old_complete", response.status_code)
        with cls.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            doc = db.get(Document, document_id)
            chunks = db.query(Chunk).count()
            print("final_job", job.status, "attempts", job.attempts)
            print("final_document", doc.status)
            print("chunks", chunks)
    finally:
        PostgresClaimTests.tearDownClass()


if __name__ == "__main__":
    main()
