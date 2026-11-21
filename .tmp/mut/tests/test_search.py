"""FR-5: гибридный поиск (FTS + Qdrant + RRF), фильтры, изоляция, similar.

BGE-M3 не скачивается: `ATLAS_EMBEDDINGS=fake` + `QdrantClient(':memory:')`.
"""
import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text as sql_text

from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.knowledge import indexer
from app.backend.main import create_app
from app.backend.models import Chunk, Document, Project, Sphere, User
from tests.test_migrations import find_pg_bin, free_port, remove_tree, upgrade

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}

VACATION = "Планирую отпуск к морю этим летом. Бюджет поездки две тысячи. Атлас."
VACATION_COPY = "Планирую отпуск к морю этим летом. Бюджет поездки три тысячи. Атлас."
FINANCE = "Квартальный финансовый отчёт: выручка выросла на десять процентов. Атлас."
GARDEN = "Полив помидоров в теплице утром, подкормка раз в неделю. Атлас."


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(
            os.environ,
            {
                "ATLAS_EMBEDDINGS": "fake",
                "ATLAS_QDRANT_URL": ":memory:",
                "ATLAS_COLLECTION": "test_chunks",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        indexer.reset_client()
        self.addCleanup(indexer.reset_client)

        url = f"sqlite:///{(Path(self.tmp.name) / 'search.db').as_posix()}"
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
            db.flush()
            self.alice_id, self.bob_id = alice.id, bob.id
            sphere = Sphere(owner_id=alice.id, name="Личное")
            bob_sphere = Sphere(owner_id=bob.id, name="Боб")
            db.add_all([sphere, bob_sphere])
            db.flush()
            self.sphere_id = sphere.id
            self.bob_sphere_id = bob_sphere.id
            project = Project(owner_id=alice.id, sphere_id=sphere.id, name="Отпуск")
            db.add(project)
            db.commit()
            self.project_id = project.id

        self.vacation = self._document(
            self.alice_id,
            "Отпуск",
            VACATION,
            sphere_id=self.sphere_id,
            project_id=self.project_id,
            doc_class="note",
            status="ready",
            tags=["отдых"],
            created_at=datetime(2026, 6, 1),
        )
        self.finance = self._document(
            self.alice_id,
            "Финансы",
            FINANCE,
            sphere_id=self.sphere_id,
            doc_class="report",
            status="ready",
            tags=["финансы"],
            created_at=datetime(2026, 7, 1),
        )
        self.garden = self._document(
            self.alice_id,
            "Сад",
            GARDEN,
            doc_class="note",
            status="needs_review",
            tags=["сад"],
            created_at=datetime(2026, 8, 1),
        )

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

    def _document(self, owner_id: str, title: str, text: str, **fields) -> int:
        fields.setdefault("tags", [])
        fields.setdefault("entities", {})
        with self.app.state.SessionLocal() as db:
            document = Document(owner_id=owner_id, title=title, **fields)
            db.add(document)
            db.flush()
            db.add(
                Chunk(
                    document_id=document.id,
                    owner_id=owner_id,
                    ord=0,
                    text=text,
                    tokens=len(text.split()),
                )
            )
            db.commit()
            indexer.index_document(db, document)
            return document.id

    def _search(self, client: TestClient | None = None, **params):
        return (client or self.alice).get("/api/search", params=params)

    def _document_ids(self, response) -> list[int]:
        self.assertEqual(response.status_code, 200, response.text)
        return [item["document_id"] for item in response.json()]

    # ---------- доступ и валидация ----------

    def test_requires_session(self) -> None:
        with TestClient(self.app) as anonymous:
            self.assertEqual(
                anonymous.get("/api/search", params={"q": "атлас"}).status_code, 401
            )
            self.assertEqual(
                anonymous.get(f"/api/documents/{self.vacation}/similar").status_code,
                401,
            )

    def test_empty_query_is_422(self) -> None:
        for params in ({}, {"q": ""}, {"q": "   "}):
            with self.subTest(params=params):
                self.assertEqual(
                    self.alice.get("/api/search", params=params).status_code, 422
                )

    def test_other_owner_sees_nothing(self) -> None:
        self.assertEqual(
            self.bob.get("/api/search", params={"q": "атлас"}).json(), []
        )
        self.assertEqual(
            self.bob.get("/api/search", params={"q": "помидоров"}).json(), []
        )
        self.assertEqual(
            self.bob.get(f"/api/documents/{self.vacation}/similar").status_code, 404
        )
        self.assertEqual(
            self.bob.get("/api/documents/999999/similar").status_code, 404
        )

    def test_foreign_filter_is_404(self) -> None:
        response = self._search(q="атлас", sphere_id=self.bob_sphere_id)
        self.assertEqual(response.status_code, 404, response.text)

    # ---------- поиск ----------

    def test_lexical_hit_and_rrf_no_duplicates(self) -> None:
        response = self._search(q="помидоров")
        results = response.json()
        self.assertTrue(results)
        self.assertEqual(results[0]["document_id"], self.garden)
        self.assertIn("помидор", results[0]["text"])
        chunk_ids = [item["chunk_id"] for item in results]
        # чанк найден и лексикой, и векторами — RRF не дублирует его
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))
        self.assertEqual(chunk_ids.count(results[0]["chunk_id"]), 1)
        self.assertEqual(results[0]["title"], "Сад")
        self.assertEqual(results[0]["status"], "needs_review")
        self.assertEqual(results[0]["tags"], ["сад"])
        self.assertGreater(results[0]["score"], 0)

    def test_semantic_hit_with_fake_dense(self) -> None:
        # «отпускной» не находится лексикой (в тексте — «отпуск»), но dense
        # видит общие 3-граммы; запрос находит документ по смыслу, не по слову.
        self.assertNotIn("отпускной", VACATION)
        results = self._search(q="отпускной").json()
        self.assertTrue(results)
        self.assertEqual(results[0]["document_id"], self.vacation)

    def test_filters_restrict_results(self) -> None:
        def ids(**params) -> set[int]:
            return set(self._document_ids(self._search(q="атлас", **params)))

        self.assertEqual(ids(), {self.vacation, self.finance, self.garden})
        self.assertEqual(ids(sphere_id=self.sphere_id), {self.vacation, self.finance})
        self.assertEqual(ids(project_id=self.project_id), {self.vacation})
        self.assertEqual(ids(status="needs_review"), {self.garden})
        self.assertEqual(ids(**{"class": "report"}), {self.finance})
        self.assertEqual(ids(tags="сад"), {self.garden})
        self.assertEqual(ids(**{"from": "2026-07-15T00:00:00"}), {self.garden})
        self.assertEqual(
            ids(**{"to": "2026-07-15T00:00:00"}), {self.vacation, self.finance}
        )
        self.assertEqual(ids(type="url"), set())

    def test_degrades_to_lexical_without_qdrant(self) -> None:
        with mock.patch.dict(os.environ, {"ATLAS_QDRANT_URL": "http://127.0.0.1:9"}):
            indexer.reset_client()
            response = self._search(q="помидоров")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["document_id"] for item in response.json()], [self.garden])

    # ---------- similar ----------

    def test_similar_returns_other_documents_only(self) -> None:
        copy = self._document(
            self.alice_id,
            "Отпуск копия",
            VACATION_COPY,
            doc_class="note",
            status="ready",
        )
        response = self.alice.get(f"/api/documents/{self.vacation}/similar")
        self.assertEqual(response.status_code, 200, response.text)
        document_ids = [item["document_id"] for item in response.json()]
        self.assertTrue(document_ids)
        self.assertEqual(document_ids[0], copy)
        self.assertNotIn(self.vacation, document_ids)
        self.assertEqual(len(document_ids), len(set(document_ids)))

    def test_similar_of_unindexed_document_is_empty(self) -> None:
        with self.app.state.SessionLocal() as db:
            document = Document(
                owner_id=self.alice_id, title="Без чанков", tags=[], entities={}
            )
            db.add(document)
            db.commit()
            document_id = document.id
        response = self.alice.get(f"/api/documents/{document_id}/similar")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])


class PostgresSearchTests(unittest.TestCase):
    """PG-FTS (шаг 4 плана): без PostgreSQL тест пропускается (как в test_migrations)."""

    def test_fts_search_on_temporary_cluster(self) -> None:
        binaries = find_pg_bin()
        if binaries is None:
            self.skipTest(
                "PostgreSQL не найден: задайте PG_BIN (initdb.exe и pg_ctl.exe)"
            )
        initdb, pg_ctl = binaries
        tmp = Path(tempfile.mkdtemp(prefix="atlas-pg-search-"))
        data = tmp / "data"
        log = tmp / "postgres.log"
        pg_ctl_log = tmp / "pg_ctl.log"
        port = free_port()
        try:
            result = subprocess.run(
                [
                    str(initdb),
                    "-D",
                    str(data),
                    "-U",
                    "postgres",
                    "-A",
                    "trust",
                    "-E",
                    "UTF8",
                    "--no-locale",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with pg_ctl_log.open("w") as out:
                result = subprocess.run(
                    [
                        str(pg_ctl),
                        "start",
                        "-D",
                        str(data),
                        "-l",
                        str(log),
                        "-o",
                        f"-p {port} -c listen_addresses=127.0.0.1",
                        "-w",
                        "-t",
                        "60",
                    ],
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                )
            if result.returncode != 0:
                self.fail(
                    "pg_ctl start:\n"
                    + pg_ctl_log.read_text(errors="replace")
                    + (log.read_text(errors="replace") if log.exists() else "")
                )
            base = f"postgresql+psycopg://postgres@127.0.0.1:{port}"
            admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
            try:
                with admin.connect() as conn:
                    conn.execute(sql_text("CREATE DATABASE atlas"))
            finally:
                admin.dispose()
            url = f"{base}/atlas"
            upgrade(url)

            with mock.patch.dict(
                os.environ,
                {
                    "ATLAS_EMBEDDINGS": "fake",
                    "ATLAS_QDRANT_URL": ":memory:",
                    "ATLAS_COLLECTION": "test_chunks_pg",
                },
            ):
                indexer.reset_client()
                self.addCleanup(indexer.reset_client)
                app = create_app(url)
                self.addCleanup(app.state.engine.dispose)
                client = TestClient(app)
                self.addCleanup(client.close)
                with app.state.SessionLocal() as db:
                    user = User(
                        username="alice", password_hash=hash_password("alice-pass")
                    )
                    db.add(user)
                    db.commit()
                    owner_id = user.id
                login = client.post(
                    "/api/auth/login",
                    json={"username": "alice", "password": "alice-pass"},
                )
                self.assertEqual(login.status_code, 200, login.text)

                def add(title: str, body: str) -> int:
                    with app.state.SessionLocal() as db:
                        document = Document(
                            owner_id=owner_id,
                            title=title,
                            tags=[],
                            entities={},
                            status="ready",
                        )
                        db.add(document)
                        db.flush()
                        db.add(
                            Chunk(
                                document_id=document.id,
                                owner_id=owner_id,
                                ord=0,
                                text=body,
                                tokens=len(body.split()),
                            )
                        )
                        db.commit()
                        indexer.index_document(db, document)
                        return document.id

                add("Сад", "Полив помидоров помидоров в теплице утром.")
                add("Отчёт", "Квартальный отчёт помидоров: выручка выросла.")

                # to_tsvector/plainto_tsquery + ts_rank: повтор слова — выше.
                results = client.get("/api/search", params={"q": "помидоров"}).json()
                self.assertEqual(results[0]["title"], "Сад", results)
                # русская морфология: «теплицы» находит «теплице».
                stems = client.get("/api/search", params={"q": "теплицы"}).json()
                self.assertIn("Сад", [item["title"] for item in stems])
                self.assertEqual(
                    client.get("/api/search", params={"q": "  "}).status_code, 422
                )
        finally:
            if (data / "postmaster.pid").exists():
                subprocess.run(
                    [
                        str(pg_ctl),
                        "stop",
                        "-D",
                        str(data),
                        "-m",
                        "immediate",
                        "-w",
                        "-t",
                        "60",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=120,
                )
            remove_tree(tmp)


if __name__ == "__main__":
    unittest.main()