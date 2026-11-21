import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ingest  # noqa: E402


class IngestTests(unittest.TestCase):
    def test_fixtures_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = ingest.run(
                ROOT / "tests" / "fixtures" / "inbox",
                tmp / "processed",
                tmp / "meta",
            )
            self.assertEqual(report["counts"]["scanned"], 10)
            self.assertEqual(report["counts"]["processed"], 10)
            self.assertEqual(report["counts"]["duplicate"], 0)
            self.assertEqual(report["counts"]["error"], 0)
            self.assertEqual(len(list((tmp / "processed").glob("*.md"))), 10)

            records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in (tmp / "meta").glob("*.json")
                if path.name != "index.json"
            ]
            self.assertEqual(len(records), 10)
            for record in records:
                self.assertEqual(len(record["content_hash"]), 64)
                self.assertTrue(record["title"])
                self.assertGreater(record["word_count"], 0)
                self.assertEqual(record["quality"], "ok")

            index = json.loads(
                (tmp / "meta" / "index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(index["hashes"]), 10)
            self.assertEqual(len(index["docs"]), 10)

    def test_documents_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = ingest.run(
                ROOT / "tests" / "fixtures" / "docs",
                tmp / "processed",
                tmp / "meta",
            )
            self.assertEqual(report["counts"]["scanned"], 10)
            self.assertEqual(report["counts"]["processed"], 10)
            self.assertEqual(report["counts"]["needs_review"], 0)
            self.assertEqual(report["counts"]["error"], 0)

            records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in (tmp / "meta").glob("*.json")
                if path.name != "index.json"
            ]
            pdfs = [record for record in records if record["format"] == "pdf"]
            images = [record for record in records if record["format"] == "png"]
            self.assertEqual(len(pdfs), 5)
            self.assertEqual(len(images), 5)
            for record in pdfs:
                self.assertGreaterEqual(record["pages"], 1)
                self.assertIn("pymupdf", record["engine"])
            for record in images:
                self.assertEqual(record["ocr_pages"], 1)
                self.assertEqual(record["engine"], "tesseract")
                self.assertGreaterEqual(record["word_count"], 1)

    def test_blank_image_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "inbox"
            source.mkdir()
            Image.new("RGB", (400, 200), "white").save(source / "blank.png")

            report = ingest.run(source, tmp / "processed", tmp / "meta")

            self.assertEqual(report["counts"]["needs_review"], 1)
            self.assertEqual(report["counts"]["processed"], 0)
            self.assertEqual(len(list((tmp / "processed").glob("*.md"))), 0)

    def test_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "inbox"
            source.mkdir()
            for i in range(3):
                (source / f"{i}.md").write_text(
                    f"---\ntitle: Note {i}\n---\n\nBody {i}\n",
                    encoding="utf-8",
                )

            first = ingest.run(source, tmp / "processed", tmp / "meta")
            second = ingest.run(source, tmp / "processed", tmp / "meta")

            self.assertEqual(first["counts"]["processed"], 3)
            self.assertEqual(second["counts"]["processed"], 0)
            self.assertEqual(second["counts"]["duplicate"], 3)
            self.assertEqual(len(list((tmp / "processed").glob("*.md"))), 3)

    def test_empty_body_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "inbox"
            source.mkdir()
            (source / "empty.md").write_text(
                "---\ntitle: Empty\n---\n\n",
                encoding="utf-8",
            )

            report = ingest.run(source, tmp / "processed", tmp / "meta")

            self.assertEqual(report["counts"]["needs_review"], 1)
            self.assertEqual(report["counts"]["processed"], 0)
            self.assertEqual(report["counts"]["skipped"], 0)
            self.assertEqual(len(list((tmp / "processed").glob("*.md"))), 0)


if __name__ == "__main__":
    unittest.main()
