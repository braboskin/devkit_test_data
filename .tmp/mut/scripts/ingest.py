"""Ingestion в Atlas: Markdown, PDF, изображения, DOCX.

Извлечение — в `app/backend/knowledge/extract.py`; здесь запись
`processed/<doc_id>.md` и `meta/<doc_id>.json` и `index.json`
для дедупликации по content_hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.knowledge.extract import (  # noqa: E402
    SUPPORTED,
    extract_file,
    normalize_body,
)

DEFAULT_SOURCE = ROOT / "data" / "inbox"
DEFAULT_PROCESSED = ROOT / "data" / "processed"
DEFAULT_META = ROOT / "data" / "meta"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, fallback: str = "doc") -> str:
    text = text.strip().lower()
    text = "".join(TRANSLIT.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_index(meta_dir: Path) -> dict:
    path = meta_dir / "index.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("hashes", {})
            data.setdefault("docs", {})
            return data
        except json.JSONDecodeError:
            pass
    return {"hashes": {}, "docs": {}}


def extract_document(path: Path) -> dict:
    return extract_file(path)


def ingest_file(
    path: Path,
    source_root: Path,
    processed_dir: Path,
    meta_dir: Path,
    index: dict,
    dry_run: bool = False,
) -> dict:
    try:
        extracted = extract_document(path)
    except Exception as exc:
        return {"status": "error", "path": str(path), "reason": str(exc)}

    body = normalize_body(extracted.get("text", ""))
    quality = extracted.get("quality", "ok")
    reason = extracted.get("reason", "")

    try:
        rel = path.relative_to(source_root)
    except ValueError:
        rel = Path(path.name)

    if not body:
        return {
            "status": "needs_review",
            "path": rel.as_posix(),
            "reason": reason or "no text extracted",
        }

    digest = sha256_text(body)
    existing = index["hashes"].get(digest)
    if existing and (processed_dir / f"{existing}.md").exists():
        return {
            "status": "duplicate",
            "doc_id": existing,
            "path": rel.as_posix(),
        }

    meta = extracted.get("meta") or {}
    title = str(
        extracted.get("title") or meta.get("title") or path.stem
    ).strip() or path.stem
    doc_id = existing or f"{slugify(title)}-{digest[:8]}"
    base = doc_id
    suffix_n = 1
    while doc_id in index["docs"] and index["docs"][doc_id].get("content_hash") != digest:
        suffix_n += 1
        doc_id = f"{base}-{suffix_n}"

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(tag) for tag in tags]

    record = {
        "doc_id": doc_id,
        "title": title,
        "source_path": rel.as_posix(),
        "source_file": path.name,
        "format": extracted.get("format", path.suffix.lstrip(".").lower()),
        "pages": extracted.get("pages"),
        "ocr_pages": extracted.get("ocr_pages", 0),
        "engine": extracted.get("engine", "unknown"),
        "content_hash": digest,
        "size_bytes": len(body.encode("utf-8")),
        "word_count": len(re.findall(r"\w+", body, flags=re.UNICODE)),
        "line_count": body.count("\n"),
        "tags": tags,
        "frontmatter": meta,
        "ingested_at": now_iso(),
        "quality": quality,
        "quality_reason": reason,
    }

    if not dry_run:
        processed_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        (processed_dir / f"{doc_id}.md").write_text(body, encoding="utf-8")
        save_json(meta_dir / f"{doc_id}.json", record)
        index["hashes"][digest] = doc_id
        index["docs"][doc_id] = record
        save_json(meta_dir / "index.json", index)

    return {
        "status": "processed" if quality == "ok" else "needs_review",
        "doc_id": doc_id,
        "path": rel.as_posix(),
        "quality": quality,
    }


def run(
    source: Path,
    processed: Path | None = None,
    meta: Path | None = None,
    dry_run: bool = False,
    report_path: Path | None = None,
) -> dict:
    source = Path(source)
    processed = Path(processed or DEFAULT_PROCESSED)
    meta = Path(meta or DEFAULT_META)

    if not source.exists():
        raise FileNotFoundError(source)

    if source.is_file():
        files = [source]
        source_root = source.parent
    else:
        files = sorted(
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED
        )
        source_root = source

    index = load_index(meta)
    results = [
        ingest_file(path, source_root, processed, meta, index, dry_run=dry_run)
        for path in files
    ]

    counts = {
        "scanned": len(files),
        "processed": 0,
        "needs_review": 0,
        "duplicate": 0,
        "skipped": 0,
        "error": 0,
    }
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    report = {
        "generated_at": now_iso(),
        "source": str(source),
        "processed": str(processed),
        "meta": str(meta),
        "dry_run": dry_run,
        "counts": counts,
        "results": results,
    }
    if report_path:
        save_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestion Markdown/PDF/изображений")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report_path = args.report or (args.meta / "ingest-report.json")
    try:
        report = run(
            source=args.source,
            processed=args.processed,
            meta=args.meta,
            dry_run=args.dry_run,
            report_path=report_path,
        )
    except FileNotFoundError as exc:
        parser.error(f"source not found: {exc}")

    if not args.quiet:
        print(json.dumps(report["counts"], ensure_ascii=False))
        for result in report["results"]:
            if result["status"] in ("error", "skipped", "needs_review"):
                print(
                    f"{result['status']}: {result['path']} — "
                    f"{result.get('reason', '')}"
                )

    return 0 if report["counts"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
