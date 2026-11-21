"""Probe: worker token survives password reset (session invalidation only)."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
os.environ["ATLAS_EMBEDDINGS"] = "fake"
os.environ["ATLAS_QDRANT_URL"] = ":memory:"
os.environ["ATLAS_COLLECTION"] = f"skeptic_{uuid.uuid4().hex}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.backend.auth import delete_user_sessions, hash_password  # noqa: E402
from app.backend.db import Base  # noqa: E402
from app.backend.main import create_app  # noqa: E402
from app.backend.models import User, WorkerToken  # noqa: E402

tmp = tempfile.TemporaryDirectory()
app = create_app(f"sqlite:///{(Path(tmp.name) / 'probe.db').as_posix()}")
Base.metadata.create_all(app.state.engine)
with app.state.SessionLocal() as db:
    user = User(username="alice", password_hash=hash_password("alice-pass"))
    db.add(user)
    db.commit()
    alice_id = user.id

client = TestClient(app)
assert client.post("/api/auth/login", json={"username": "alice", "password": "alice-pass"}).status_code == 200
token = client.post("/api/settings/worker-token").json()["token"]
buf = io.BytesIO()
Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
assert client.post("/api/documents", files={"file": ("scan.png", buf.getvalue(), "image/png")}).status_code == 200

with app.state.SessionLocal() as db:
    delete_user_sessions(db, alice_id)
    print("worker_tokens_after_reset", db.query(WorkerToken).filter_by(owner_id=alice_id).count())

print("session_after_reset", client.get("/api/me").status_code)
r = client.post("/api/worker/claim", headers={"Authorization": f"Bearer {token}"})
print("old_worker_token_claim", r.status_code, (r.json().get("job") or {}).get("id") if r.status_code == 200 else r.text)

app.state.engine.dispose()
tmp.cleanup()
