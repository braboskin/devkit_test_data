"""A3: приёмка M2 без реальной BGE-M3 (fake embeddings + in-memory Qdrant).

Сценарии: текстовый PDF сразу `ready` и находится поиском; «скан» уходит в
job `extract`, воркер забирает/завершает его → документ `ready`, чанки и
поиск; отмена queued-job → `cancelled` + документ `failed`; A11 smoke —
порог Яндекс.Диска переключает storage (детали в `test_yadisk`).
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import pymupdf
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image

from app.backend import config, yadisk
from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.knowledge import indexer
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Job, User
from app.backend.routers import documents

ALICE = {"username": "alice", "password": "alice-pass"}
PDF_MARKER = "kryptonite"
PDF_TEXT = (
    "Acceptance report for the Atlas knowledge base.\n\n"
    f"Unique token {PDF_MARKER} appears exactly once in this small PDF.\n\n"
    "The extraction pipeline must mark this document as ready without OCR.\n"
)
WORKER_MARKER = "mellotron"
WORKER_TEXT = (
    "Распознанный скан: договор с ООО «Ромашка». "
    f"Маркер {WORKER_MARKER}, дата 12.03.2026."
)


def make_png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def make_pdf(text: str, title: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 520, 720), text, fontsize=14, fontname="helv"
    )
    document.set_metadata({"title": title})
    data = document.tobytes()
    document.close()
    return data


class IngestAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage_dir = Path(self.tmp.name) / "storage"

        env = mock.patch.dict(
            os.environ,
            {
                "ATLAS_EMBEDDINGS": "fake",
                "ATLAS_QDRANT_URL": ":memory:",
                "ATLAS_COLLECTION": f"test_ingest_acceptance_{uuid.uuid4().hex}",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        indexer.reset_client()
        self.addCleanup(indexer.reset_client)

        previous_key = os.environ.get("ATLAS_FERNET_KEY")
        os.environ["ATLAS_FERNET_KEY"] = Fernet.generate_key().decode()

        def restore_key() -> None:
            if previous_key is None:
                os.environ.pop("ATLAS_FERNET_KEY", None)
            else:
                os.environ["ATLAS_FERNET_KEY"] = previous_key

        self.addCleanup(restore_key)

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
            db.add(alice)
            db.commit()
            self.alice_id = alice.id

        storage_patch = mock.patch.object(config, "STORAGE_DIR", self.storage_dir)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)

        self.alice = TestClient(self.app)
        self.addCleanup(self.alice.close)
        self._login()

    # ---------- helpers ----------

    def _login(self) -> None:
        response = self.alice.post("/api/auth/login", json=ALICE)
        self.assertEqual(response.status_code, 200, response.text)

    def _ok(self, response, code: int = 200) -> dict:
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _upload(
        self,
        name: str,
        content: bytes,
        content_type: str = "text/markdown",
        **data: object,
    ):
        return self.alice.post(
            "/api/documents",
            files={"file": (name, content, content_type)},
            data={key: str(value) for key, value in data.items()},
        )

    def _token(self) -> str:
        return self._ok(
            self.alice.post("/api/settings/worker-token"), 201
        )["token"]

    @staticmethod
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _job_id(self) -> int:
        with self.app.state.SessionLocal() as db:
            job = (
                db.query(Job)
                .filter_by(owner_id=self.alice_id)
                .order_by(Job.id.desc())
                .first()
            )
            self.assertIsNotNone(job)
            return job.id

    def _search_ids(self, query: str) -> list[int]:
        return [
            item["document_id"]
            for item in self._ok(
                self.alice.get("/api/search", params={"q": query})
            )
        ]

    # ---------- 1. текстовый PDF ----------

    def test_text_pdf_is_ready_and_searchable(self) -> None:
        body = self._ok(
            self._upload(
                "report.pdf",
                make_pdf(PDF_TEXT, "Acceptance report"),
                "application/pdf",
            )
        )
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["pages"], 1)
        self.assertEqual(body["title"], "Acceptance report")
        self.assertEqual(body["source_type"], "file")
        self.assertEqual(body["storage"], "local")
        self.assertIsNone(body["error"])

        content = self.alice.get(f"/api/documents/{body['id']}/content")
        self.assertEqual(content.status_code, 200, content.text)
        self.assertIn(PDF_MARKER, content.text)

        # fake embeddings + in-memory Qdrant: чанк проиндексирован и найден.
        self.assertIn(body["id"], self._search_ids(PDF_MARKER))
        with self.app.state.SessionLocal() as db:
            chunks = (
                db.query(Chunk)
                .filter_by(document_id=body["id"])
                .order_by(Chunk.ord)
                .all()
            )
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.owner_id == self.alice_id for chunk in chunks))
            self.assertTrue(all(chunk.qdrant_point_id for chunk in chunks))

    # ---------- 2. скан → job → воркер ----------

    def test_scan_job_claim_complete_makes_document_ready(self) -> None:
        png = make_png()
        body = self._ok(self._upload("scan.png", png, "image/png"))
        self.assertEqual(body["status"], "queued")
        job_id = self._job_id()

        jobs = self._ok(self.alice.get("/api/jobs"))
        self.assertEqual(
            [(job["id"], job["type"], job["status"]) for job in jobs],
            [(job_id, "extract", "queued")],
        )

        token = self._token()
        claimed = self._ok(
            self.alice.post("/api/worker/claim", headers=self._auth(token))
        )
        self.assertEqual(claimed["job"]["id"], job_id)
        self.assertEqual(claimed["job"]["status"], "running")
        self.assertEqual(claimed["document"]["id"], body["id"])

        original = self.alice.get(
            f"/api/worker/jobs/{job_id}/file", headers=self._auth(token)
        )
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.content, png)

        done = self._ok(
            self.alice.post(
                f"/api/worker/jobs/{job_id}/complete",
                json={"text": WORKER_TEXT, "pages": 1, "quality": "ok"},
                headers=self._auth(token),
            )
        )
        self.assertEqual(done["status"], "done")

        document = self._ok(self.alice.get(f"/api/documents/{body['id']}"))
        self.assertEqual(document["status"], "ready")
        self.assertEqual(document["pages"], 1)
        self.assertIsNone(document["error"])
        content = self.alice.get(f"/api/documents/{body['id']}/content").text
        self.assertIn(WORKER_MARKER, content)

        # Чанки есть, проиндексированы и находятся поиском.
        with self.app.state.SessionLocal() as db:
            chunks = db.query(Chunk).filter_by(document_id=body["id"]).all()
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.qdrant_point_id for chunk in chunks))
        self.assertIn(body["id"], self._search_ids(WORKER_MARKER))
        self.assertEqual(
            [job["id"] for job in self._ok(
                self.alice.get("/api/jobs", params={"status": "done"})
            )],
            [job_id],
        )

    # ---------- 3. отмена ----------

    def test_cancel_queued_job_fails_document(self) -> None:
        body = self._ok(self._upload("scan.png", make_png("gray"), "image/png"))
        self.assertEqual(body["status"], "queued")
        job_id = self._job_id()

        cancelled = self._ok(self.alice.post(f"/api/jobs/{job_id}/cancel"))
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNotNone(cancelled["finished_at"])

        document = self._ok(self.alice.get(f"/api/documents/{body['id']}"))
        self.assertEqual(document["status"], "failed")
        self.assertEqual(document["error"], "cancelled")

        # Отменённое задание больше не забирается воркером.
        token = self._token()
        self.assertEqual(
            self.alice.post(
                "/api/worker/claim", headers=self._auth(token)
            ).status_code,
            204,
        )
        self.assertEqual(
            self.alice.post(f"/api/jobs/{job_id}/cancel").status_code, 409
        )

    # ---------- 4. A11: порог Яндекс.Диска (smoke) ----------

    def test_yadisk_threshold_storage_switch(self) -> None:
        note = (
            "---\ntitle: Локальная заметка\n---\n\n"
            "Текст про бюджет проекта на второй квартал.\n"
        )
        with mock.patch.object(documents, "YADISK_THRESHOLD", 10):
            local = self._ok(self._upload("local.md", note.encode("utf-8")))
        # Без токена интеграции оригинал остаётся локальным.
        self.assertEqual(local["storage"], "local")
        self.assertIsNone(local["error"])

        remote_note = (
            "---\ntitle: Удалённая заметка\n---\n\n"
            "Текст про отпуск и поездку к морю в июле.\n"
        )
        token = "y0_AgAcceptance-token-1234"
        self.assertEqual(
            self._ok(self.alice.put("/api/settings/yadisk", json={"token": token}))[
                "masked"
            ],
            "***1234",
        )
        with (
            mock.patch.object(documents, "YADISK_THRESHOLD", 10),
            mock.patch.object(yadisk, "upload_file") as upload,
        ):
            remote = self._ok(self._upload("remote.md", remote_note.encode("utf-8")))
            upload.assert_called_once()
        self.assertEqual(remote["storage"], "yandex")
        self.assertTrue(remote["storage_ref"].startswith(f"disk:/atlas/{self.alice_id}/"))
        self.assertEqual(upload.call_args.args[0], token)
        self.assertEqual(remote["storage_ref"], f"disk:{upload.call_args.args[1]}")

        # Оригинал при этом не потерян: локальная копия на месте.
        with self.app.state.SessionLocal() as db:
            document = db.get(Document, remote["id"])
            self.assertEqual(document.storage, "yandex")
            self.assertTrue(
                (
                    self.storage_dir
                    / self.alice_id
                    / f"{remote['id']}.md"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
