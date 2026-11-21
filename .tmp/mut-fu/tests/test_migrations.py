"""Миграции M1/M2: таблицы §7 и `owner_id` — на SQLite и PostgreSQL."""
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"

# Все таблицы §7: M1 (пользователи, сессии, домен) + M2 (знания).
TABLES = {
    "users",
    "sessions",
    "spheres",
    "projects",
    "people",
    "person_spheres",
    "person_projects",
    "tasks",
    "task_dependencies",
    "task_people",
    "events",
    "event_participants",
    "calendar_tokens",
    "documents",
    "chunks",
    "jobs",
    "worker_tokens",
    "integrations",
}
# Доменные таблицы, у которых обязателен owner_id (task_dependencies — через tasks).
OWNER_TABLES = TABLES - {"users", "sessions", "task_dependencies"}


def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def upgrade(url: str) -> None:
    with mock.patch.dict(os.environ, {"ATLAS_DB_URL": url}):
        command.upgrade(alembic_config(), "head")


def assert_schema(test: unittest.TestCase, url: str) -> None:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        test.assertEqual(
            set(inspector.get_table_names()) - {"alembic_version"},
            TABLES,
        )
        for table in sorted(OWNER_TABLES):
            columns = {col["name"] for col in inspector.get_columns(table)}
            test.assertIn("owner_id", columns, f"{table} без owner_id")
    finally:
        engine.dispose()


def assert_knowledge_indexes(test: unittest.TestCase, url: str) -> None:
    """Индексы 0002: дедуп по sha256 и выборки по владельцу."""
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        documents = {index["name"] for index in inspector.get_indexes("documents")}
        test.assertTrue(
            {
                "ix_documents_owner_created",
                "ix_documents_owner_status",
                "uq_documents_owner_sha256",
            }
            <= documents,
            documents,
        )
        chunks = {index["name"] for index in inspector.get_indexes("chunks")}
        test.assertIn("ix_chunks_owner_document_ord", chunks)
        jobs = {index["name"] for index in inspector.get_indexes("jobs")}
        test.assertTrue(
            {"ix_jobs_owner_status", "ix_jobs_status_created"} <= jobs, jobs
        )
    finally:
        engine.dispose()


def assert_pg_knowledge(test: unittest.TestCase, url: str) -> None:
    """PG-специфика 0002: partial unique по sha256 и GIN FTS по тексту."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            defs = dict(
                conn.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE tablename IN ('chunks', 'documents')"
                    )
                ).all()
            )
    finally:
        engine.dispose()
    fts = defs.get("ix_chunks_text_fts", "")
    test.assertIn("using gin", fts.lower())
    test.assertIn("to_tsvector", fts.lower())
    test.assertIn("russian", fts.lower())
    test.assertIn("where", defs.get("uq_documents_owner_sha256", "").lower())


class SqliteMigrationTests(unittest.TestCase):
    def test_upgrade_head_creates_m1_m2_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "atlas.db"
            url = f"sqlite:///{db.as_posix()}"
            upgrade(url)
            assert_schema(self, url)
            assert_knowledge_indexes(self, url)


def _exe(directory: Path, name: str) -> Path | None:
    for candidate in (directory / f"{name}.exe", directory / name):
        if candidate.is_file():
            return candidate
    return None


def find_pg_bin() -> tuple[Path, Path] | None:
    """initdb и pg_ctl: PG_BIN, стандартный путь PostgreSQL 17 или PATH."""
    candidates: list[Path] = []
    if os.environ.get("PG_BIN"):
        candidates.append(Path(os.environ["PG_BIN"]))
    candidates.append(Path(r"C:\Program Files\PostgreSQL\17\bin"))
    for name in ("initdb", "initdb.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).parent)
            break
    for directory in candidates:
        initdb = _exe(directory, "initdb")
        pg_ctl = _exe(directory, "pg_ctl")
        if initdb and pg_ctl:
            return initdb, pg_ctl
    return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def remove_tree(path: Path) -> None:
    for _ in range(10):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.3)


class PostgresMigrationTests(unittest.TestCase):
    def test_upgrade_head_on_temporary_cluster(self) -> None:
        binaries = find_pg_bin()
        if binaries is None:
            self.skipTest(
                "PostgreSQL не найден: задайте PG_BIN (initdb.exe и pg_ctl.exe)"
            )
        initdb, pg_ctl = binaries
        tmp = Path(tempfile.mkdtemp(prefix="atlas-pg-"))
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

            # stdout/stderr — в файлы, не в pipe: демон их наследует, и
            # communicate() на pipe не дождётся EOF.
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
                server_log = log.read_text(errors="replace") if log.exists() else ""
                self.fail(
                    "pg_ctl start:\n"
                    + pg_ctl_log.read_text(errors="replace")
                    + server_log
                )

            base = f"postgresql+psycopg://postgres@127.0.0.1:{port}"
            admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
            try:
                with admin.connect() as conn:
                    conn.execute(text("CREATE DATABASE atlas"))
            finally:
                admin.dispose()

            url = f"{base}/atlas"
            upgrade(url)
            assert_schema(self, url)
            assert_knowledge_indexes(self, url)
            assert_pg_knowledge(self, url)

            engine = create_engine(url)
            try:
                inspector = inspect(engine)
                columns = {
                    col["name"]: col for col in inspector.get_columns("people")
                }
                self.assertIsInstance(columns["contacts"]["type"], JSONB)
                self.assertIsInstance(columns["tags"]["type"], JSONB)
                document_columns = {
                    col["name"]: col for col in inspector.get_columns("documents")
                }
                self.assertIsInstance(document_columns["tags"]["type"], JSONB)
                self.assertIsInstance(document_columns["entities"]["type"], JSONB)
            finally:
                engine.dispose()
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
