"""FR-4: загрузка документов, дедуп, лимит, изоляция, URL-режим."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config, storage
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Job, User
from app.backend.routers import documents as documents_router

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}

MD = (
    "---\ntitle: Заметка\n---\n\n"
    "Иван Петров обсудил бюджет проекта 12.03.2026 в г. Москва. #финансы\n"
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

    def test_duplicate_race_returns_existing(self) -> None:
        """F7: конкурент вставил тот же sha256 между проверкой и commit."""
        sha256 = hashlib.sha256(MD.encode("utf-8")).hexdigest()
        with self._db() as db:
            existing = Document(
                owner_id=self.alice_id,
                title="race.md",
                mime="text/markdown",
                size_bytes=len(MD),
                sha256=sha256,
                storage="none",
                status="ready",
                tags=[],
                entities={},
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
            existing_id = existing.id

        real_find = documents_router._find_duplicate
        calls = {"count": 0}

        def racing_find(db, owner_id, value):
            calls["count"] += 1
            # Первая проверка — окно гонки: «дубля ещё нет».
            return None if calls["count"] == 1 else real_find(db, owner_id, value)

        with mock.patch.object(
            documents_router, "_find_duplicate", side_effect=racing_find
        ):
            body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        self.assertTrue(body["duplicate"])
        self.assertEqual(body["id"], existing_id)
        self.assertGreaterEqual(calls["count"], 2)
        with self._db() as db:
            self.assertEqual(
                db.query(Document).filter_by(owner_id=self.alice_id).count(), 1
            )
        owner_dir = self.storage_dir / self.alice_id
        self.assertEqual(
            [path for path in owner_dir.iterdir()] if owner_dir.is_dir() else [],
            [],
        )

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

    # ---------- безопасные ошибки и индексация ----------

    def test_processing_error_has_no_details(self) -> None:
        """F8: в `document.error` только категория, без путей/URL/секретов."""
        body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        leak = (
            f"OSError: {self.storage_dir}/secret.txt "
            "https://example.com/x?token=SECRET"
        )
        with mock.patch.object(
            documents_router, "analyze_file", side_effect=OSError(leak)
        ):
            response = self.alice.post(f"/api/documents/{body['id']}/reprocess")
        self.assertEqual(response.status_code, 500, response.text)
        card = self._ok(self.alice.get(f"/api/documents/{body['id']}"))
        self.assertEqual(card["status"], "failed")
        self.assertEqual(card["error"], "extract failed")
        for fragment in (str(self.storage_dir), "https://", "SECRET", "OSError"):
            self.assertNotIn(fragment, card["error"])

    def test_error_categories(self) -> None:
        self.assertEqual(
            documents_router._error_category(storage.StorageLimitExceeded()),
            "too large",
        )
        self.assertEqual(
            documents_router._error_category(ValueError("unsupported format: .xml")),
            "unsupported format",
        )
        self.assertEqual(
            documents_router._error_category(
                ValueError(f"cannot read {self.storage_dir}/x")
            ),
            "extract failed",
        )
        self.assertEqual(
            documents_router._error_category(
                RuntimeError("https://example.com/?token=SECRET")
            ),
            "extract failed",
        )

    def test_index_failure_is_visible_and_reindex_recovers(self) -> None:
        """F9: сбой индексации не молчит; reindex повторяет индексацию."""
        with mock.patch.object(
            documents_router, "index_document", side_effect=RuntimeError("qdrant down")
        ):
            body = self._ok(self._upload(self.alice, "note.md", MD.encode("utf-8")))
        self.assertEqual(body["error"], "indexing failed")
        self.assertEqual(body["status"], "ready")
        with self._db() as db:
            self.assertEqual(db.get(Document, body["id"]).error, "indexing failed")
            self.assertTrue(
                all(
                    chunk.qdrant_point_id is None
                    for chunk in db.query(Chunk)
                    .filter_by(document_id=body["id"])
                    .all()
                )
            )

        response = self.alice.post(f"/api/documents/{body['id']}/reindex")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["error"])
        with self._db() as db:
            chunks = db.query(Chunk).filter_by(document_id=body["id"]).all()
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.qdrant_point_id for chunk in chunks))

        with mock.patch.object(
            documents_router, "index_document", side_effect=RuntimeError("down again")
        ):
            failed = self.alice.post(f"/api/documents/{body['id']}/reindex")
        self.assertEqual(failed.status_code, 502, failed.text)
        self.assertEqual(
            self._ok(self.alice.get(f"/api/documents/{body['id']}"))["error"],
            "indexing failed",
        )

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
            ("post", f"/api/documents/{document_id}/reindex"),
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

    def test_url_mode(self) -> None:
        with mock.patch(
            "app.backend.http_fetch.fetch_text",
            return_value=("Иван Петров обсудил бюджет проекта.", "Статья про бюджет"),
        ) as fetch:
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
        self.assertEqual(fetch.call_args.args, ("http://example.com/article",))
        self.assertEqual(
            fetch.call_args.kwargs,
            {
                "max_bytes": config.MAX_UPLOAD_BYTES,
                "max_chars": documents_router.MAX_URL_TEXT_CHARS,
                "timeout": config.FETCH_TIMEOUT_SECONDS,
            },
        )
        content = self.alice.get(f"/api/documents/{body['id']}/content").text
        self.assertIn("Иван Петров", content)
        # Оригинала на диске нет: скачивание из сети — не блокер (409, не 500).
        self.assertEqual(
            self.alice.get(f"/api/documents/{body['id']}/file").status_code, 409
        )

    def test_url_fetch_errors_are_mapped(self) -> None:
        """`HttpFetchError` из SSRF-модуля → HTTP-статус без документа."""
        from app.backend import http_fetch

        cases = (
            (422, "url points to a private address"),
            (422, "url content type is not supported"),
            (422, "url returned 404"),
            (413, "url content exceeds 2048 bytes"),
        )
        for status, detail in cases:
            with self.subTest(detail=detail):
                with mock.patch(
                    "app.backend.http_fetch.fetch_text",
                    side_effect=http_fetch.HttpFetchError(status, detail),
                ):
                    response = self.alice.post(
                        "/api/documents", data={"url": "http://example.com/x"}
                    )
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.json()["detail"], detail)
        # Реальная проверка схемы срабатывает без сети.
        self.assertEqual(
            self.alice.post(
                "/api/documents", data={"url": "file:///etc/passwd"}
            ).status_code,
            422,
        )
        with self._db() as db:
            self.assertEqual(db.query(Document).count(), 0)

    # ---------- нативный лимит тела запроса (F3) ----------

    def _limited_client(self, mb: int = 1) -> TestClient:
        """App с маленьким `max_body_size`: лимит читается в `create_app`."""
        from app.backend import main as main_module

        url = f"sqlite:///{(Path(self.tmp.name) / 'limit.db').as_posix()}"
        with mock.patch.object(main_module, "MAX_UPLOAD_MB", mb):
            app = create_app(url)
        self.addCleanup(app.state.engine.dispose)
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_content_length_rejected_before_parsing(self) -> None:
        client = self._limited_client()
        response = client.post(
            "/api/documents",
            content=b"x" * (3 * 1024 * 1024),
            headers={"content-type": "multipart/form-data; boundary=xyz"},
        )
        self.assertEqual(response.status_code, 413, response.text)
        with client.app.state.SessionLocal() as db:
            self.assertEqual(db.query(Document).count(), 0)

    def test_chunked_body_rejected_before_parsing(self) -> None:
        """Без Content-Length: нативный лимит считает фактические байты."""
        client = self._limited_client()
        response = client.post(
            "/api/auth/login",
            content=(b"x" * (1024 * 1024) for _ in range(3)),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413, response.text)

    def test_storage_stream_limit(self) -> None:
        """Chunked-тело: второй рубеж — лимит при стриминге на диск."""
        with self.assertRaises(storage.StorageLimitExceeded):
            storage.save_stream(io.BytesIO(b"x" * 100), self.alice_id, 10)
        leftovers = (
            list(self.storage_dir.rglob("tmp-*"))
            if self.storage_dir.exists()
            else []
        )
        self.assertEqual(leftovers, [])

    # ---------- A11/FR-4: оригинал в Яндексе и lifecycle ----------

    def _upload_as_yandex(self, name: str, content: bytes) -> dict:
        """Загрузка с моком выгрузки в облако: `storage='yandex'`, копия локально."""

        def fake_store(db, user, document, local_path):
            document.storage = "yandex"
            document.storage_ref = (
                f"disk:/atlas/{user.id}/{document.id}{Path(local_path).suffix}"
            )
            db.commit()
            return True

        with (
            mock.patch.object(documents_router, "YADISK_THRESHOLD", 10),
            mock.patch("app.backend.yadisk.store_original", side_effect=fake_store),
        ):
            return self._ok(self._upload(self.alice, name, content))

    def test_yandex_original_is_served_locally(self) -> None:
        body = self._upload_as_yandex("remote.md", MD.encode("utf-8"))
        self.assertEqual(body["storage"], "yandex")
        self.assertTrue(body["storage_ref"].startswith("disk:/atlas/"))
        document_id = body["id"]

        original = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.content, MD.encode("utf-8"))
        self.assertEqual(
            self._ok(self.alice.post(f"/api/documents/{document_id}/reprocess"))[
                "status"
            ],
            "ready",
        )

        # F5: удаление убирает локальную копию и при storage='yandex'.
        stored = self._stored(document_id, "md")
        self.assertTrue(stored.is_file())
        self.assertEqual(
            self.alice.delete(f"/api/documents/{document_id}").status_code, 204
        )
        self.assertFalse(stored.exists())
        with self._db() as db:
            self.assertIsNone(db.get(Document, document_id))

    def test_yandex_without_local_copy_is_409(self) -> None:
        body = self._upload_as_yandex(
            "remote2.md", (MD + "Второй документ про отпуск.").encode("utf-8")
        )
        document_id = body["id"]
        self._stored(document_id, "md").unlink()

        file_response = self.alice.get(f"/api/documents/{document_id}/file")
        self.assertEqual(file_response.status_code, 409, file_response.text)
        self.assertIn("external storage", file_response.json()["detail"])
        self.assertEqual(
            self.alice.post(f"/api/documents/{document_id}/reprocess").status_code,
            409,
        )

    # ---------- F10: повторная переобработка и активное задание ----------

    def test_reprocess_conflicts_with_active_job(self) -> None:
        body = self._ok(
            self._upload(self.alice, "scan.png", make_png(), "image/png")
        )
        self.assertEqual(body["status"], "queued")
        conflict = self.alice.post(f"/api/documents/{body['id']}/reprocess")
        self.assertEqual(conflict.status_code, 409, conflict.text)
        with self._db() as db:
            job_id = db.query(Job).one().id
            self.assertEqual(db.query(Job).count(), 1)

        # Отмена задания снимает блокировку — переобработка ставит новое.
        self.assertEqual(
            self.alice.post(f"/api/jobs/{job_id}/cancel").status_code, 200
        )
        reprocessed = self._ok(
            self.alice.post(f"/api/documents/{body['id']}/reprocess")
        )
        self.assertEqual(reprocessed["status"], "queued")
        with self._db() as db:
            self.assertEqual(db.query(Job).count(), 2)


if __name__ == "__main__":
    unittest.main()
