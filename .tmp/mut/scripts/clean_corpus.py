"""Удалить из data/processed и data/meta документы не из указанного источника."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Очистка корпуса по источнику")
    parser.add_argument("--keep-source", default="obsidian")
    parser.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--meta", type=Path, default=ROOT / "data" / "meta")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    kept = 0
    removed = 0
    for path in sorted(args.meta.glob("*.json")):
        if path.name in ("index.json", "ingest-report.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        source = (record.get("frontmatter") or {}).get("source")
        if source == args.keep_source:
            kept += 1
            continue
        doc_id = record.get("doc_id")
        if doc_id and not args.dry_run:
            (args.processed / f"{doc_id}.md").unlink(missing_ok=True)
        if not args.dry_run:
            path.unlink(missing_ok=True)
        removed += 1

    if not args.dry_run:
        for name in ("index.json", "ingest-report.json"):
            (args.meta / name).unlink(missing_ok=True)

    print(
        json.dumps(
            {
                "keep_source": args.keep_source,
                "kept": kept,
                "removed": removed,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
