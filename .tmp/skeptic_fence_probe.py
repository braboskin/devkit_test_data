"""Probe: an in-flight old complete is not fenced by attempts after a new claim.

The complete endpoint checks `job.attempts` when it starts (`_running_job`), then
later writes job/document by primary key. A reclaim + new claim can happen in
between; the old write has no WHERE status/attempts condition.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from tests.test_worker_pg import PostgresClaimTests  # noqa: E402
from app.backend.models import Document, Job, utcnow  # noqa: E402
from app.backend.routers import worker as worker_router  # noqa: E402


def main() -> None:
    PostgresClaimTests.setUpClass()
    try:
        cls = PostgresClaimTests
        inst = PostgresClaimTests("runTest")
        inst._clear()
        owner, token = inst._user("alice")
        inst._seed(owner, 1)
        claimed = inst._claim(token).json()["job"]
        job_id = claimed["id"]
        assert claimed["attempts"] == 1
        with cls.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            document_id = job.payload["document_id"]
            job.started_at = utcnow() - timedelta(
                minutes=worker_router.LEASE_MINUTES + 1
            )
            db.commit()

        # Old complete passed _running_job (attempts=1) and has loaded its state.
        with cls.app.state.SessionLocal() as db_old:
            job_old = db_old.get(Job, job_id)
            doc_old = db_old.get(Document, document_id)
            assert job_old.attempts == 1 and job_old.status == "running"

            # Meanwhile: reclaim stale -> queued, then a new claim -> attempts=2.
            with cls.app.state.SessionLocal() as db_reclaim:
                worker_router._reclaim_stale(db_reclaim, owner, utcnow())
            new_claim = inst._claim(token)
            print("new_claim", new_claim.status_code, new_claim.json()["job"]["attempts"])

            # Old complete commits its (already loaded) result by id.
            job_old.status = "done"
            job_old.finished_at = utcnow()
            doc_old.status = "ready"
            db_old.commit()

            with cls.app.state.SessionLocal() as db_check:
                final_job = db_check.get(Job, job_id)
                final_doc = db_check.get(Document, document_id)
                print("final_job", final_job.status, "attempts", final_job.attempts)
                print("final_document", final_doc.status)
                # The current generation (attempts=2) can no longer complete.
                late = inst._claim_token(token, job_id, attempts=2)
                print("current_generation_complete", late.status_code)
    finally:
        PostgresClaimTests.tearDownClass()


def _claim_token(self, token: str, job_id: int, attempts: int):
    from fastapi.testclient import TestClient

    client = TestClient(self.app)
    try:
        return client.post(
            f"/api/worker/jobs/{job_id}/complete",
            json={"text": "result", "attempts": attempts},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        client.close()


PostgresClaimTests._claim_token = _claim_token

if __name__ == "__main__":
    main()
