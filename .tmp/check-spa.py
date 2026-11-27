import sys

sys.path.insert(0, r"X:\devkit_projects\projects\atlas\repo\atlas")

from fastapi.testclient import TestClient

from app.backend.main import create_app

client = TestClient(create_app())

for path in ("/", "/chat", "/settings", "/nope", "/api/nope", "/health"):
    response = client.get(path)
    content_type = response.headers.get("content-type", "")
    marker = ""
    if "text/html" in content_type:
        marker = ' <div id="root">' if 'id="root"' in response.text else " (html без #root)"
    print(f"{path} -> {response.status_code} {content_type}{marker}")
