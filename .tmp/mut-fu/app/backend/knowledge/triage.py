"""Triage документов перед индексацией (v1, правила без LLM)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROCESSED = ROOT / "data" / "processed"
DEFAULT_META = ROOT / "data" / "meta"

POLICIES = {"full", "summary", "metadata_only", "skip"}
PRIORITY = {"full": 4, "summary": 3, "metadata_only": 2, "skip": 1}
SENSITIVE_TAGS = {"private", "sensitive", "секрет", "личное"}
IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"}
SPHERE_MAP = {
    "1. здоровье и тело": "health",
    "2. работа и продуктивность": "career",
    "3. финансы": "finance",
    "4. отношения и социум": "relationships",
    "5. развитие и обучение": "development",
    "6. быт и рутина": "home",
    "7. отдых и впечатления": "rest",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def detect_language(text: str) -> str:
    sample = text[:1000]
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    total = cyrillic + latin
    if total == 0:
        return "unknown"
    if cyrillic / total >= 0.6:
        return "ru"
    if latin / total >= 0.6:
        return "en"
    return "mixed"


def make_summary(text: str, max_chars: int = 600) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"[*_`>]+", "", line)
        lines.append(line)
        if len(" ".join(lines)) >= max_chars:
            break
    summary = " ".join(lines).strip()
    if not summary:
        summary = re.sub(r"[#*_`>]+", " ", text).strip()
    return summary[:max_chars].strip()


def classify(record: dict, text: str) -> dict:
    frontmatter = record.get("frontmatter") or {}
    source_path = str(
        record.get("source_path") or frontmatter.get("obsidian_path") or ""
    )
    path = source_path.replace("\\", "/")
    parts = PurePosixPath(path).parts
    lower_parts = [part.lower() for part in parts]
    lower = path.lower()

    doc_type = "note"
    sphere = None
    project = None
    policy = "full"
    reason = "default"

    if any(part in {".obsidian", ".git", "_system"} for part in lower_parts):
        doc_type = "template"
        policy = "skip"
        reason = "system path"
    elif lower_parts and lower_parts[0].startswith("5. archive"):
        doc_type = "archive"
        policy = "metadata_only"
        reason = "archive path"
    elif lower_parts and lower_parts[0].startswith("4. journal"):
        doc_type = "journal"
        policy = "summary"
        reason = "journal path"
    elif lower_parts and lower_parts[0].startswith("3. resources"):
        doc_type = "resource"
        reason = "resources path"
    elif lower_parts and lower_parts[0].startswith("1. projects"):
        doc_type = "project"
        if len(parts) > 1:
            project = PurePosixPath(parts[1]).stem
        reason = "projects path"
    elif lower_parts and lower_parts[0].startswith("2. areas"):
        doc_type = "area"
        if len(lower_parts) > 1:
            sphere = SPHERE_MAP.get(lower_parts[1])
        if "инвест" in lower:
            sphere = "investments"
        elif "финанс" in lower and sphere is None:
            sphere = "finance"
        reason = "areas path"
    elif lower_parts and lower_parts[0].startswith("0. inbox"):
        doc_type = "inbox"
        reason = "inbox path"
    else:
        data_format = str(record.get("format") or "").lower()
        if data_format == "pdf":
            doc_type = "document"
        elif data_format in IMAGE_FORMATS:
            doc_type = "image"
        elif data_format in {"md", "markdown"}:
            doc_type = "note"
        reason = f"format {data_format}" if data_format else "default"

    quality = str(record.get("quality") or "ok")
    if "старое" in lower or "разобрать" in lower:
        quality = "needs_review"

    text_length = len(text.strip())
    if text_length < 40 or int(record.get("word_count") or 0) < 5:
        quality = "needs_review"
        if policy not in {"skip", "metadata_only"}:
            policy = "metadata_only"
            reason = f"{reason}; short text"

    if frontmatter.get("type"):
        doc_type = str(frontmatter["type"])
    if frontmatter.get("sphere"):
        sphere = str(frontmatter["sphere"]) or None
    if frontmatter.get("project"):
        project = str(frontmatter["project"]) or None
    override = frontmatter.get("index_policy")
    if override in POLICIES:
        policy = override
        reason = f"{reason}; frontmatter override"

    raw_tags = frontmatter.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    tags = {str(tag).lower().lstrip("#") for tag in raw_tags}
    sensitive = (
        "sensitive"
        if frontmatter.get("sensitive") is True or tags & SENSITIVE_TAGS
        else "normal"
    )

    return {
        "type": doc_type,
        "sphere": sphere,
        "project": project,
        "index_policy": policy,
        "quality": quality,
        "sensitive": sensitive,
        "language": detect_language(text),
        "summary": make_summary(text),
        "reason": reason,
        "triaged_at": now_iso(),
    }


def run(
    processed: Path = DEFAULT_PROCESSED,
    meta: Path = DEFAULT_META,
    report_path: Path | None = None,
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    records: list[tuple[Path, dict]] = []
    errors: list[dict] = []

    for path in sorted(meta.glob("*.json")):
        if path.name in ("index.json", "triage-report.json", "ingest-report.json"):
            continue
        if limit and len(records) >= limit:
            break
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": path.name, "reason": str(exc)})
            continue
        doc_id = record.get("doc_id") or path.stem
        text_path = processed / f"{doc_id}.md"
        if not text_path.exists():
            errors.append({"doc_id": doc_id, "reason": "processed not found"})
            continue
        try:
            text = text_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append({"doc_id": doc_id, "reason": str(exc)})
            continue
        record["triage"] = classify(record, text)
        records.append((path, record))

    duplicates = 0
    by_hash: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for item in records:
        content_hash = item[1].get("content_hash")
        if content_hash:
            by_hash[content_hash].append(item)

    for group in by_hash.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: item[1].get("doc_id", ""))
        canonical = max(
            ordered,
            key=lambda item: PRIORITY.get(item[1]["triage"]["index_policy"], 0),
        )
        for path, record in ordered:
            if record is canonical[1]:
                continue
            record["triage"]["index_policy"] = "skip"
            record["triage"]["reason"] = (
                f"{record['triage']['reason']}; duplicate of "
                f"{canonical[1].get('doc_id', '')}"
            )
            duplicates += 1

    by_policy = Counter(record["triage"]["index_policy"] for _, record in records)
    by_type = Counter(record["triage"]["type"] for _, record in records)
    by_sphere = Counter(
        record["triage"]["sphere"] or "none" for _, record in records
    )
    by_quality = Counter(record["triage"]["quality"] for _, record in records)

    report = {
        "generated_at": now_iso(),
        "docs": len(records),
        "duplicates": duplicates,
        "counts": {
            "by_policy": dict(by_policy),
            "by_type": dict(by_type),
            "by_sphere": dict(by_sphere),
            "by_quality": dict(by_quality),
        },
        "errors": errors,
        "decisions": [
            {
                "doc_id": record.get("doc_id"),
                "source_path": record.get("source_path"),
                "type": record["triage"]["type"],
                "sphere": record["triage"]["sphere"],
                "project": record["triage"]["project"],
                "index_policy": record["triage"]["index_policy"],
                "quality": record["triage"]["quality"],
                "sensitive": record["triage"]["sensitive"],
                "language": record["triage"]["language"],
                "reason": record["triage"]["reason"],
            }
            for _, record in records
        ],
    }

    if not dry_run:
        for path, record in records:
            save_json(path, record)
        if report_path:
            save_json(report_path, report)

    return report


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Triage документов Atlas")
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    report_path = args.report or (args.meta / "triage-report.json")
    report = run(
        processed=args.processed,
        meta=args.meta,
        report_path=report_path,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "docs": report["docs"],
                "duplicates": report["duplicates"],
                "counts": report["counts"],
                "errors": len(report["errors"]),
            },
            ensure_ascii=False,
        )
    )
    return 0
