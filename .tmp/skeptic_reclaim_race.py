"""Probe: `_reclaim_stale` read-modify-write by id can clobber a concurrent complete.

Uses the temporary PG cluster from tests.test_worker_pg; simulates the reclaim
UPDATE between its SELECT and commit (the code modifies ORM objects then commits
by primary key, without rechecking status/started_at).
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from unittest import mock

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
        claimed = inst._claim(token)
        job_id = claimed.json()["job"]["id"]
        with cls.app.state.SessionLocal() as db:
            job = db.get(Job, job_id)
            document_id = job.payload["document_id"]
            # stale, original worker still (about to) complete
            job.started_at = utcnow() - timedelta(
                minutes=worker_router.LEASE_MINUTES + 1
            )
            db.commit()

        # Session A mimics `_reclaim_stale`: SELECT stale, modify queued, pause.
        with cls.app.state.SessionLocal() as db_a:
            job_a = db_a.get(Job, job_id)
            doc_a = db_a.get(Document, document_id)
            job_a.status = "queued"
            job_a.started_at = None
            job_a.error = None
            doc_a.status = "queued"

            # Original worker completes before A commits.
            with mock.patch.object(worker_router, "index_document"):
                completed = inst._claim_token(token, job_id)
            print("concurrent_complete", completed.status_code)

            db_a.commit()
            with cls.app.state.SessionLocal() as db_check:
                print("after_reclaim_commit_job", db_check.get(Job, job_id).status)
                print(
                    "after_reclaim_commit_finished_at",
                    db_check.get(Job, job_id).finished_at,
                )
                print(
                    "after_reclaim_commit_document",
                    db_check.get(Document, document_id).status,
                )
    finally:
        PostgresClaimTests.tearDownClass()


def _claim_token(self, token: str, job_id: int):
    from fastapi.testclient import TestClient

    client = TestClient(self.app)
    try:
        return client.post(
            f"/api/worker/jobs/{job_id}/complete",
            json={"text": "worker result"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        client.close()


PostgresClaimTests._claim_token = _claim_token

if __name__ == "__main__":
    main()
