"""FR-4: загрузка документов, дедуп, лимит, изоляция, URL-режим."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Job, User

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}

MD = (
    "---\ntitle: Заметка\n---\n\n"
    "Иван Петров обсудил бюджет проекта 12.03.2026 в г. Москва. #финансы\n"
)
HTML = (
    "<html><head><title>Статья про бюджет</title>"
    "<style>p{color:red}</style></head><body>"
    "<p>Иван Петров обсудил бюджет проекта 12.03.2026.</p>"
    "<script>var hidden = 1;</script></body></html>"
)


def make_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class DocumentTests(unittest.TestCase):
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

    def _upload(
        self,
        client: TestClient,
        name: str,
        content: bytes,
        content_type: str = "text/markdown",
        **data: object,
    ):
        return client.post(
            "/api/documents",
            files={"file": (name, content, content_type)},
            data={key: str(value) for key, value in data.items()},
        )

    def _ok(self, response, code: int = 200) -> dict:
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _stored(self, document_id: int, ext: str) -> Path:
        return self.storage_dir / self.alice_id / f"{document_id}.{ext}"

    def _db(self):
        return self.app.state.SessionLocal()

    # ---------- быстрый путь ----------

    def test_markdown_upload_is_ready(self) -> None:
        body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        self.assertFalse(body["duplicate"])
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["source_type"], "file")
        self.assertEqual(body["storage"], "local")
        self.assertEqual(body["title"], "Заметка")
        self.assertTrue(body["annotation"])
        self.assertIn("финансы", body["tags"])
        self.assertIn("Иван Петров", body["entities"]["people"])
        self.assertEqual(body["error"], None)

        with self._db() as db:
            chunks = (
                db.query(Chunk).filter_by(document_id=body["id"]).order_by(Chunk.ord).all()
            )
            self.assertTrue(chunks)
            self.assertIn("Иван Петров", " ".join(c.text for c in chunks))
        self.assertTrue(self._stored(body["id"], "md").is_file())

        content = self.alice.get(f"/api/documents/{body['id']}/content")
        self.assertEqual(content.status_code, 200, content.text)
        self.assertTrue(content.headers["content-type"].startswith("text/markdown"))
        self.assertIn("Иван Петров", content.text)

        original = self.alice.get(f"/api/documents/{body['id']}/file")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original.content, MD.encode("utf-8"))

    def test_txt_upload_is_ready(self) -> None:
        body = self._ok(
            self._upload(
                self.alice,
                "заметка.txt",
                "Встреча с ООО «Ромашка» 12.03.2026 в г. Москва.".encode("utf-8"),
                "text/plain",
            )
        )
        self.assertEqual(body["status"], "ready")
        self.assertIn("Встреча", self.alice.get(
            f"/api/documents/{body['id']}/content"
        ).text)

    # ---------- отложенный путь ----------

    def test_png_upload_is_queued_for_worker(self) -> None:
        body = self._ok(
            self._upload(self.alice, "scan.png", make_png(), "image/png")
        )
        self.assertEqual(body["status"], "queued")
        self.assertTrue(self._stored(body["id"], "png").is_file())
        with self._db() as db:
            job = db.query(Job).one()
            self.assertEqual(job.status, "queued")
            self.assertEqual(job.type, "extract")
            self.assertEqual(
                job.payload,
                {
                    "document_id": body["id"],
                    "storage_ref": body["storage_ref"],
                    "kind": "extract",
                },
            )
            self.assertEqual(db.query(Chunk).count(), 0)

    # ---------- дедуп и лимит ----------

    def test_duplicate_within_owner_only(self) -> None:
        first = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        second = self._ok(self._upload(self.alice, "copy.md", MD.encode("utf-8")))
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["id"], first["id"])
        with self._db() as db:
            self.assertEqual(db.query(Document).filter_by(owner_id=self.alice_id).count(), 1)
        self.assertEqual(
            len(list((self.storage_dir / self.alice_id).iterdir())), 1
        )

        # У второго владельца тот же контент — свой документ, не дубль.
        bob = self._ok(self._upload(self.bob, "note.md", MD.encode("utf-8")))
        self.assertFalse(bob["duplicate"])
        self.assertNotEqual(bob["id"], first["id"])

    def test_upload_limit(self) -> None:
        with (
            mock.patch.object(config, "MAX_UPLOAD_BYTES", 10),
            mock.patch.object(config, "MAX_UPLOAD_MB", 1),
        ):
            response = self._upload(self.alice, "big.md", b"x" * 100)
        self.assertEqual(response.status_code, 413, response.text)
        with self._db() as db:
            self.assertEqual(db.query(Document).count(), 0)
        leftovers = (
            [path for path in self.storage_dir.rglob("tmp-*")]
            if self.storage_dir.exists()
            else []
        )
        self.assertEqual(leftovers, [])

    # ---------- доступ ----------

    def test_requires_session(self) -> None:
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.get("/api/documents").status_code, 401)
            self.assertEqual(
                anonymous.post(
                    "/api/documents",
                    files={"file": ("note.md", MD.encode("utf-8"), "text/markdown")},
                ).status_code,
                401,
            )

    def test_foreign_document_is_404(self) -> None:
        body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        document_id = body["id"]
        self.assertEqual(self.bob.get("/api/documents").json(), [])
        for method, path in (
            ("get", f"/api/documents/{document_id}"),
            ("get", f"/api/documents/{document_id}/content"),
            ("get", f"/api/documents/{document_id}/file"),
            ("post", f"/api/documents/{document_id}/reprocess"),
            ("delete", f"/api/documents/{document_id}"),
        ):
            with self.subTest(path=path):
                response = getattr(self.bob, method)(path)
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(
            self.alice.get(f"/api/documents/{document_id}").status_code, 200
        )

    def test_foreign_sphere_filter_and_target_404(self) -> None:
        bob_sphere = self._ok(self.bob.post("/api/spheres", json={"name": "Боб"}), 201)
        self.assertEqual(
            self.alice.get(
                "/api/documents", params={"sphere_id": bob_sphere["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self._upload(
                self.alice, "note.md", MD.encode("utf-8"), sphere_id=bob_sphere["id"]
            ).status_code,
            404,
        )

    # ---------- валидация входа ----------

    def test_bad_upload_requests(self) -> None:
        self.assertEqual(self.alice.post("/api/documents", data={}).status_code, 422)
        self.assertEqual(
            self.alice.post(
                "/api/documents",
                files={"file": ("note.md", MD.encode("utf-8"), "text/markdown")},
                data={"url": "http://example.com/"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self._upload(
                self.alice, "virus.exe", b"MZ", "application/octet-stream"
            ).status_code,
            422,
        )

    # ---------- переобработка и удаление ----------

    def test_reprocess_and_delete(self) -> None:
        body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        document_id = body["id"]
        stored = self._stored(document_id, "md")

        # Переобработка читает оригинал заново: подменяем файл на диске.
        stored.write_text(
            "Совсем другой текст про отпуск 01.02.2026.", encoding="utf-8"
        )
        reprocessed = self._ok(
            self.alice.post(f"/api/documents/{document_id}/reprocess")
        )
        self.assertEqual(reprocessed["status"], "ready")
        content = self.alice.get(f"/api/documents/{document_id}/content").text
        self.assertIn("Совсем другой", content)
        self.assertNotIn("Иван Петров", content)
        with self._db() as db:
            chunks = db.query(Chunk).filter_by(document_id=document_id).all()
            self.assertTrue(chunks)
            self.assertIn("Совсем другой", " ".join(c.text for c in chunks))

        self.assertEqual(
            self.alice.delete(f"/api/documents/{document_id}").status_code, 204
        )
        self.assertFalse(stored.exists())
        with self._db() as db:
            self.assertIsNone(db.get(Document, document_id))
            self.assertEqual(db.query(Chunk).filter_by(document_id=document_id).count(), 0)
        self.assertEqual(
            self.alice.delete(f"/api/documents/{document_id}").status_code, 404
        )
        self.assertEqual(
            self.alice.get(f"/api/documents/{document_id}").status_code, 404
        )

    # ---------- список и фильтры ----------

    def test_list_filters(self) -> None:
        ready = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        queued = self._ok(
            self._upload(self.alice, "scan.png", make_png(), "image/png")
        )

        def ids(**params: object) -> list[int]:
            return sorted(
                item["id"] for item in self._ok(self.alice.get("/api/documents", params=params))
            )

        self.assertEqual(ids(), sorted([ready["id"], queued["id"]]))
        self.assertEqual(ids(status="queued"), [queued["id"]])
        self.assertEqual(ids(status="ready"), [ready["id"]])
        self.assertEqual(ids(tag="финансы"), [ready["id"]])
        self.assertEqual(ids(q="бюджет"), [ready["id"]])
        self.assertEqual(ids(q="нет такого"), [])
        self.assertEqual(ids(**{"from": "2020-01-01T00:00:00"}), sorted(
            [ready["id"], queued["id"]]
        ))
        self.assertEqual(ids(**{"to": "2020-01-01T00:00:00"}), [])

    # ---------- URL-режим ----------

    def test_url_mode_and_ssrf(self) -> None:
        response = httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
        with (
            mock.patch("app.backend.routers.documents._public_host"),
            mock.patch(
                "app.backend.routers.documents.httpx.get", return_value=response
            ),
        ):
            body = self._ok(
                self.alice.post(
                    "/api/documents", data={"url": "http://example.com/article"}
                )
            )
        self.assertEqual(body["source_type"], "url")
        self.assertEqual(body["storage"], "none")
        self.assertEqual(body["storage_ref"], "http://example.com/article")
        self.assertEqual(body["title"], "Статья про бюджет")
        self.assertEqual(body["status"], "ready")
        content = self.alice.get(f"/api/documents/{body['id']}/content").text
        self.assertIn("Иван Петров", content)
        self.assertNotIn("var hidden", content)
        self.assertEqual(
            self.alice.get(f"/api/documents/{body['id']}/file").status_code, 404
        )

        # SSRF: приватный адрес отклоняется до сетевого запроса.
        for url in ("http://127.0.0.1:9/x", "http://10.0.0.1/x", "file:///etc/passwd"):
            with self.subTest(url=url):
                self.assertEqual(
                    self.alice.post("/api/documents", data={"url": url}).status_code,
                    422,
                )


if __name__ == "__main__":
    unittest.main()
