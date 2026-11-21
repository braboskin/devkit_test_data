"""Тесты knowledge core: DOCX, сущности, аннотация, быстрый путь should_defer."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.backend.knowledge.annotate import annotate  # noqa: E402
from app.backend.knowledge.entities import extract_entities  # noqa: E402
from app.backend.knowledge.extract import extract_file  # noqa: E402
from app.backend.knowledge.pipeline import (  # noqa: E402
    analyze_file,
    should_defer,
)

SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def make_pdf(path: Path, pages: int = 1, text: str | None = None) -> None:
    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page()
        if text:
            page.insert_textbox(
                pymupdf.Rect(72, 72, 520, 720),
                text,
                fontsize=14,
                fontname="helv",
            )
    document.save(path)
    document.close()


class DocxTests(unittest.TestCase):
    def test_docx_text_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.docx"
            from docx import Document

            document = Document()
            document.add_heading("Отчёт по проекту", level=1)
            document.add_paragraph(
                "Иван Петров подготовил отчёт 12.03.2026 для ООО «Ромашка»."
            )
            table = document.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "Показатель"
            table.cell(0, 1).text = "Значение"
            document.save(path)

            data = extract_file(path)
            self.assertEqual(data["format"], "docx")
            self.assertEqual(data["engine"], "python-docx")
            self.assertEqual(data["quality"], "ok")
            self.assertIn("Иван Петров", data["text"])
            self.assertIn("Показатель | Значение", data["text"])

            analyzed = analyze_file(path, "report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.assertFalse(analyzed["needs_review"])
            self.assertTrue(analyzed["annotation"])
            self.assertEqual(analyzed["doc_class"], "note")


class EntitiesTests(unittest.TestCase):
    TEXT = (
        "Встреча с ООО «Ромашка» прошла в г. Москва 12.03.2026. "
        "Обсуждали бюджет проекта #проект #финансы. "
        "Иван Петров вёл встречу."
    )

    def test_entities_found(self):
        entities = extract_entities(self.TEXT, frontmatter={"tags": ["Планы"]})
        self.assertIn("Иван Петров", entities["people"])
        self.assertTrue(any("Ромашка" in org for org in entities["orgs"]))
        self.assertIn("г. Москва", entities["places"])
        self.assertIn("12.03.2026", entities["dates"])
        self.assertIn("проект", entities["tags"])
        self.assertIn("финансы", entities["tags"])
        self.assertIn("планы", entities["tags"])

    def test_entities_have_no_duplicates(self):
        entities = extract_entities(
            self.TEXT + " Иван Петров, ООО «Ромашка», 12.03.2026, #проект."
        )
        for name, values in entities.items():
            with self.subTest(name=name):
                self.assertEqual(
                    len(values), len({value.casefold() for value in values})
                )

    def test_iso_and_written_dates(self):
        entities = extract_entities("Срок 2026-03-12, затем 12 марта 2026.")
        self.assertIn("2026-03-12", entities["dates"])
        self.assertIn("12 марта 2026", entities["dates"])


class AnnotateTests(unittest.TestCase):
    TEXT = (
        "Команда закрыла первый этап проекта. "
        "Иван Петров отметил рост скорости. "
        "Следующий шаг — нагрузочное тестирование. "
        "Это предложение не должно попасть в аннотацию."
    )

    def test_annotation_is_one_to_three_sentences(self):
        result = annotate(
            self.TEXT,
            {
                "format": "md",
                "source_path": "3. Resources/book.md",
                "frontmatter": {"tags": ["Планы"]},
            },
        )
        sentences = [s for s in SENTENCE_RE.split(result["annotation"]) if s]
        self.assertGreaterEqual(len(sentences), 1)
        self.assertLessEqual(len(sentences), 3)
        self.assertTrue(result["annotation"].endswith("."))
        self.assertNotIn("не должно попасть", result["annotation"])
        self.assertEqual(result["doc_class"], "resource")
        self.assertIn("планы", result["tags"])
        self.assertIn("Иван Петров", result["entities"]["people"])

    def test_annotation_from_empty_text(self):
        result = annotate("", {"format": "md", "source_path": "x.md"})
        self.assertEqual(result["annotation"], "")
        self.assertTrue(result["doc_class"])


class PipelineTests(unittest.TestCase):
    TEXT_PDF = "Text layer for the fast path. Second sentence of the document."

    def test_text_pdf_fast_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.pdf"
            make_pdf(path, pages=1, text=self.TEXT_PDF)

            decision = should_defer(path, "application/pdf", path.stat().st_size)
            self.assertFalse(decision["defer"])
            self.assertIsNone(decision["kind"])

            analyzed = analyze_file(path, "note.pdf", "application/pdf")
            self.assertFalse(analyzed["needs_review"])
            self.assertEqual(analyzed["doc_class"], "document")
            self.assertEqual(analyzed["pages"], 1)
            self.assertTrue(analyzed["annotation"])

    def test_scan_pdf_defers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            make_pdf(path, pages=2)

            decision = should_defer(path, "application/pdf", path.stat().st_size)
            self.assertTrue(decision["defer"])
            self.assertEqual(decision["kind"], "extract")

    def test_big_pdf_defers_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.pdf"
            make_pdf(path, pages=21, text=self.TEXT_PDF)

            decision = should_defer(path, "application/pdf", path.stat().st_size)
            self.assertTrue(decision["defer"])
            self.assertEqual(decision["kind"], "extract-full")

    def test_image_defers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.png"
            Image.new("RGB", (300, 100), "white").save(path)

            decision = should_defer(path, "image/png", path.stat().st_size)
            self.assertTrue(decision["defer"])
            self.assertEqual(decision["kind"], "extract")

    def test_markdown_does_not_defer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.md"
            path.write_text(
                "---\ntitle: Планы\n---\n\n"
                "Иван Петров обсудил бюджет 12.03.2026 в г. Москва. #финансы\n",
                encoding="utf-8",
            )

            decision = should_defer(
                path, "text/markdown", path.stat().st_size
            )
            self.assertFalse(decision["defer"])

            analyzed = analyze_file(path, "0. Inbox/note.md", "text/markdown")
            self.assertEqual(analyzed["title"], "Планы")
            self.assertEqual(analyzed["doc_class"], "inbox")
            self.assertFalse(analyzed["needs_review"])
            self.assertIn("Иван Петров", analyzed["entities"]["people"])
            self.assertIn("финансы", analyzed["tags"])


if __name__ == "__main__":
    unittest.main()
