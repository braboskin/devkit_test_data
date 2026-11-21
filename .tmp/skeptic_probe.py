"""Skeptic probes: worker fail detail leak + SQLite concurrent claim."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

os.environ["ATLAS_EMBEDDINGS"] = "fake"
os.environ["ATLAS_QDRANT_URL"] = ":memory:"
os.environ["ATLAS_COLLECTION"] = f"skeptic_{uuid.uuid4().hex}"
os.environ["ATLAS_FERNET_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.backend import config  # noqa: E402
from app.backend.auth import hash_password  # noqa: E402
from app.backend.db import Base  # noqa: E402
from app.backend.main import create_app  # noqa: E402
from app.backend.models import Document, Job, User, WorkerToken  # noqa: E402

tmp = tempfile.TemporaryDirectory()
db_path = Path(tmp.name) / "probe.db"
app = create_app(f"sqlite:///{db_path.as_posix()}")
Base.metadata.create_all(app.state.engine)
with app.state.SessionLocal() as db:
    user = User(username="alice", password_hash=hash_password("alice-pass"))
    db.add(user)
    db.commit()
    alice_id = user.id

client = TestClient(app)
r = client.post("/api/auth/login", json={"username": "alice", "password": "alice-pass"})
assert r.status_code == 200, r.text
token = client.post("/api/settings/worker-token").json()["token"]
auth = {"Authorization": f"Bearer {token}"}

def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()

# --- Probe 1: worker fail stores arbitrary detail (F8) ---
up = client.post(
    "/api/documents", files={"file": ("scan.png", png(), "image/png")}
).json()
claimed = client.post("/api/worker/claim", headers=auth).json()
leak = (
    "FileNotFoundError: [Errno 2] No such file or directory: "
    "C:\\Users\\alice\\AppData\\Local\\Temp\\secret-scan.png "
    "https://example.com/x?token=SECRET_TOKEN"
)
fail = client.post(
    f"/api/worker/jobs/{claimed['job']['id']}/fail",
    json={"error": leak},
    headers=auth,
)
card = client.get(f"/api/documents/{up['id']}").json()
job = client.get("/api/jobs", params={"status": "failed"}).json()[0]
print("PROBE1 fail_status", fail.status_code)
print("PROBE1 document.error =", repr(card["error"]))
print("PROBE1 job.error =", repr(job["error"]))
print("PROBE1 contains_path", "C:\\Users" in (card["error"] or ""))
print("PROBE1 contains_secret", "SECRET_TOKEN" in (card["error"] or ""))

# --- Probe 2: SQLite concurrent claim ---
double_claims = 0
errors = 0
for i in range(6):
    with app.state.SessionLocal() as db:
        db.query(Job).delete()
        db.query(Document).delete()
        db.commit()
        docs = []
        for _ in range(2):
            d = Document(
                owner_id=alice_id, title="d.png", mime="image/png",
                size_bytes=1, storage="none", status="queued", tags=[], entities={},
            )
            db.add(d)
            db.flush()
            db.add(Job(owner_id=alice_id, type="ocr", status="queued",
                       payload={"document_id": d.id, "kind": "ocr"}))
            docs.append(d.id)
        db.commit()
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def run():
        c = TestClient(app)
        try:
            barrier.wait(timeout=10)
            rr = c.post("/api/worker/claim", headers={"Authorization": f"Bearer {token}"})
            with lock:
                results.append((rr.status_code, rr.json() if rr.status_code == 200 else rr.text[:80]))
        finally:
            c.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    with app.state.SessionLocal() as db:
        running = db.query(Job).filter_by(owner_id=alice_id, status="running").count()
        processing = db.query(Document).filter_by(owner_id=alice_id, status="processing").count()
    codes = [code for code, _ in results]
    same_job = len(results) == 2 and all(code == 200 for code in codes) and (
        results[0][1]["job"]["id"] == results[1][1]["job"]["id"]
    )
    if same_job:
        double_claims += 1
    if any(code >= 500 for code in codes):
        errors += 1
    print(f"PROBE2 iter={i} codes={codes} running={running} processing={processing} same_job={same_job}")
    if any(code >= 500 for code in codes):
        print("PROBE2 body", [body for code, body in results if code >= 500])

print("PROBE2 double_claims", double_claims, "5xx_iters", errors)

tmp.cleanup()
app.state.engine.dispose()
