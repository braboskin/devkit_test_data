"""Импорт Obsidian vault в data/inbox/obsidian."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from frontmatter import parse_frontmatter  # noqa: E402

SKIP_PARTS = {".obsidian", ".git", ".trash", "_system"}
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<![\w/])#([A-Za-zА-Яа-яЁё0-9_/-]{2,})")
ATTACHMENT_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".svg")


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def replace_wikilinks(text: str) -> str:
    def replace(match: re.Match) -> str:
        embed = match.group(1) == "!"
        inner = match.group(2).strip()
        target, _, alias = inner.partition("|")
        target = target.strip()
        alias = alias.strip()
        if target.lower().endswith(ATTACHMENT_SUFFIXES):
            return f"[вложение: {target}]"
        if target.lower().endswith(".md"):
            target = target[:-3]
        label = alias or target
        label = label.replace("#", " — ")
        return f"[{label}]" if embed else label

    return WIKILINK_RE.sub(replace, text)


def clean_body(text: str) -> str:
    text = re.sub(r"%%[\s\S]*?%%", "", text)
    text = re.sub(r"```dataview[\s\S]*?```", "", text, flags=re.I)
    text = re.sub(r"```tasks[\s\S]*?```", "", text, flags=re.I)
    text = re.sub(r"^>\s*\[![^\]]+\]\s*", "> ", text, flags=re.M)
    text = text.replace("==", "")
    text = replace_wikilinks(text)
    return text.strip()


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def note_title(body: str, stem: str, meta: dict) -> str:
    if meta.get("title"):
        return str(meta["title"])
    match = re.search(r"^#\s+(.+)$", body, re.M)
    if match:
        return match.group(1).strip()
    return stem


def note_tags(body: str, meta: dict) -> list[str]:
    raw = meta.get("tags") or []
    if isinstance(raw, str):
        raw = [raw]
    tags = {str(tag).lstrip("#") for tag in raw}
    tags.update(TAG_RE.findall(body))
    tags.add("obsidian")
    return sorted(tag for tag in tags if tag)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Импорт Obsidian vault")
    parser.add_argument("--vault", type=Path, default=Path("X:/dev/obs-vault"))
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "inbox" / "obsidian"
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--include-system", action="store_true")
    args = parser.parse_args(argv)

    if not args.vault.exists():
        parser.error(f"vault not found: {args.vault}")
    if args.clean and args.out.exists() and not args.dry_run:
        shutil.rmtree(args.out)

    skip_parts = set(SKIP_PARTS)
    if args.include_system:
        skip_parts.discard("_system")

    files = sorted(args.vault.rglob("*.md"))
    imported = 0
    skipped = 0
    empty = 0
    total_bytes = 0
    limit = args.limit or len(files)

    for path in files:
        if imported >= limit:
            break
        relative = path.relative_to(args.vault)
        if any(part in skip_parts for part in relative.parts):
            skipped += 1
            continue

        raw = read_text(path)
        meta, body = parse_frontmatter(raw)
        body = clean_body(body)
        if not body:
            empty += 1
            continue

        title = note_title(body, path.stem, meta)
        tags = note_tags(body, meta)
        frontmatter = [
            "---",
            f"title: {yaml_quote(title)}",
            f"tags: [{', '.join(tags)}]",
            "source: obsidian",
            f"obsidian_path: {yaml_quote(relative.as_posix())}",
            "---",
            "",
        ]
        content = "\n".join(frontmatter) + body + "\n"
        target = args.out / relative
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        imported += 1
        total_bytes += len(content.encode("utf-8"))

    summary = {
        "vault": str(args.vault),
        "out": str(args.out),
        "scanned": len(files),
        "imported": imported,
        "skipped": skipped,
        "empty": empty,
        "bytes": total_bytes,
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
