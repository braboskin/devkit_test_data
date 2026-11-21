"""Probe: heartbeat does not renew the stale lease; old worker can still complete."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
os.environ["ATLAS_EMBEDDINGS"] = "fake"
os.environ["ATLAS_QDRANT_URL"] = ":memory:"
os.environ["ATLAS_COLLECTION"] = f"skeptic_{uuid.uuid4().hex}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.backend.auth import hash_password  # noqa: E402
from app.backend.db import Base  # noqa: E402
from app.backend.main import create_app  # noqa: E402
from app.backend.models import Job, User, utcnow  # noqa: E402
from app.backend.routers import worker as worker_router  # noqa: E402

tmp = tempfile.TemporaryDirectory()
app = create_app(f"sqlite:///{(Path(tmp.name) / 'probe.db').as_posix()}")
Base.metadata.create_all(app.state.engine)
with app.state.SessionLocal() as db:
    user = User(username="alice", password_hash=hash_password("alice-pass"))
    db.add(user)
    db.commit()
    alice_id = user.id

c = TestClient(app)
assert c.post("/api/auth/login", json={"username": "alice", "password": "alice-pass"}).status_code == 200
token = c.post("/api/settings/worker-token").json()["token"]
auth = {"Authorization": f"Bearer {token}"}
buf = io.BytesIO()
Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
doc = c.post("/api/documents", files={"file": ("scan.png", buf.getvalue(), "image/png")}).json()
w1 = c.post("/api/worker/claim", headers=auth).json()
job_id = w1["job"]["id"]
print("claim1", w1["job"]["attempts"], w1["job"]["status"])
with app.state.SessionLocal() as db:
    job = db.get(Job, job_id)
    job.started_at = utcnow() - timedelta(minutes=worker_router.LEASE_MINUTES + 1)
    db.commit()
hb = c.post(f"/api/worker/jobs/{job_id}/heartbeat", headers=auth)
print("heartbeat", hb.status_code, hb.json())
w2 = c.post("/api/worker/claim", headers=auth)
print("claim2_after_heartbeat", w2.status_code, (w2.json().get("job") or {}).get("id"), (w2.json().get("job") or {}).get("attempts"))
# "Old" worker still holds the job id and can complete it after reclaim.
done = c.post(
    f"/api/worker/jobs/{job_id}/complete",
    json={"text": "old worker result"},
    headers=auth,
)
print("old_worker_complete_after_reclaim", done.status_code)
print("document", c.get(f"/api/documents/{doc['id']}").json()["status"])

app.state.engine.dispose()
tmp.cleanup()
