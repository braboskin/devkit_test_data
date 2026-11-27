import sys

sys.path.insert(0, r"X:\devkit_projects\projects\atlas\repo\atlas")

from fastapi.testclient import TestClient

from app.backend.core.db import SessionLocal
from app.backend.core.deps import current_user
from app.backend.main import create_app
from app.backend.models import User

app = create_app()
session = SessionLocal()
user = session.query(User).first()
print("user:", user.id, user.username)

app.dependency_overrides[current_user] = lambda: user
client = TestClient(app)
for url in (
    "/api/events?from=2026-11-01&to=2026-12-01&expand=true",
    "/api/events?from=2026-11-01T00:00:00&to=2026-12-01T00:00:00&expand=true",
):
    response = client.get(url)
    print(url, "->", response.status_code, response.text[:200])
