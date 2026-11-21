import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import triage  # noqa: E402


def write_doc(
    meta_dir: Path,
    processed_dir: Path,
    doc_id: str,
    source_path: str,
    text: str,
    content_hash: str | None = None,
    quality: str = "ok",
    extra_frontmatter: dict | None = None,
) -> None:
    (processed_dir / f"{doc_id}.md").write_text(text, encoding="utf-8")
    frontmatter = {
        "source": "obsidian",
        "obsidian_path": source_path,
        "tags": ["obsidian"],
    }
    if extra_frontmatter:
        frontmatter.update(extra_frontmatter)
    record = {
        "doc_id": doc_id,
        "title": doc_id,
        "source_path": source_path,
        "content_hash": content_hash or f"hash-{doc_id}",
        "size_bytes": len(text.encode("utf-8")),
        "word_count": len(text.split()),
        "format": "md",
        "quality": quality,
        "frontmatter": frontmatter,
    }
    (meta_dir / f"{doc_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class TriageTests(unittest.TestCase):
    def test_rules_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            meta = tmp / "meta"
            processed = tmp / "processed"
            meta.mkdir()
            processed.mkdir()

            long_text = " ".join(f"слово{i}" for i in range(80))
            write_doc(meta, processed, "archive", "5. Archive/old.md", long_text)
            write_doc(
                meta,
                processed,
                "health",
                "2. Areas/1. Здоровье и тело/sleep.md",
                long_text,
            )
            write_doc(
                meta,
                processed,
                "journal",
                "4. Journal/day.md",
                long_text,
            )
            write_doc(
                meta,
                processed,
                "system",
                "_system/template.md",
                long_text,
            )
            write_doc(meta, processed, "short", "0. Inbox/short.md", "ок")
            write_doc(
                meta,
                processed,
                "dup1",
                "0. Inbox/a.md",
                long_text,
                content_hash="same-hash",
            )
            write_doc(
                meta,
                processed,
                "dup2",
                "0. Inbox/b.md",
                long_text,
                content_hash="same-hash",
            )

            report = triage.run(
                processed=processed,
                meta=meta,
                report_path=meta / "triage-report.json",
            )

            records = {}
            for path in meta.glob("*.json"):
                if path.name in ("triage-report.json", "index.json"):
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
                records[record["doc_id"]] = record

            self.assertEqual(records["archive"]["triage"]["index_policy"], "metadata_only")
            self.assertEqual(records["archive"]["triage"]["type"], "archive")
            self.assertEqual(records["health"]["triage"]["sphere"], "health")
            self.assertEqual(records["health"]["triage"]["index_policy"], "full")
            self.assertEqual(records["journal"]["triage"]["index_policy"], "summary")
            self.assertTrue(records["journal"]["triage"]["summary"])
            self.assertEqual(records["system"]["triage"]["index_policy"], "skip")
            self.assertEqual(records["short"]["triage"]["index_policy"], "metadata_only")
            self.assertEqual(records["short"]["triage"]["quality"], "needs_review")

            dup_policies = {
                records["dup1"]["triage"]["index_policy"],
                records["dup2"]["triage"]["index_policy"],
            }
            self.assertEqual(dup_policies, {"full", "skip"})
            self.assertEqual(report["duplicates"], 1)
            self.assertEqual(report["docs"], 7)
            self.assertTrue((meta / "triage-report.json").exists())

    def test_frontmatter_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            meta = tmp / "meta"
            processed = tmp / "processed"
            meta.mkdir()
            processed.mkdir()

            write_doc(
                meta,
                processed,
                "override",
                "3. Resources/book.md",
                "Длинный текст " * 40,
                extra_frontmatter={"index_policy": "skip", "sphere": "development"},
            )
            triage.run(processed=processed, meta=meta)

            record = json.loads(
                (meta / "override.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["triage"]["index_policy"], "skip")
            self.assertEqual(record["triage"]["sphere"], "development")


if __name__ == "__main__":
    unittest.main()
