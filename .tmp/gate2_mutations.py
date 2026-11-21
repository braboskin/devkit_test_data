"""Mutation harness v2 for the M2 fix revision 5b1ebc4. Never touches the candidate."""
import hashlib
import subprocess
import sys
from pathlib import Path

MUT = Path(r"X:\devkit_instance\testproject\.tmp\mut2")
PY = Path(r"X:\devkit_instance\testproject\repo\atlas\.venv\Scripts\python.exe")

MUTATIONS = [
    # ---------- new fixes: the new tests must catch these ----------
    dict(
        name="F2 short token not fully masked",
        file="app/backend/yadisk.py",
        edits=[('    if len(raw) < 12:\n        return "***"\n',
                '    if False:\n        return "***"\n')],
        test="tests.test_yadisk.YadiskTests.test_mask_token_hides_sensitive_part",
    ),
    dict(
        name="F6 worker file ignores yandex local copy",
        file="app/backend/storage.py",
        edits=[('    if storage == "local" and storage_ref:\n',
                '    if storage != "local":\n        return None\n    if storage == "local" and storage_ref:\n')],
        test="tests.test_worker.WorkerTests.test_file_serves_local_copy_of_yandex_original",
    ),
    dict(
        name="F5 delete keeps local copy for yandex",
        file="app/backend/routers/documents.py",
        edits=[("    if local is not None:\n        local.unlink(missing_ok=True)\n",
                "    if local is not None and document.storage == \"local\":\n        local.unlink(missing_ok=True)\n")],
        test="tests.test_documents.DocumentTests.test_yandex_original_is_served_locally",
    ),
    dict(
        name="F10 reprocess ignores active job",
        file="app/backend/routers/documents.py",
        edits=[('    if _active_job(db, user, document.id) is not None:\n'
                '        raise HTTPException(\n'
                '            http_status.HTTP_409_CONFLICT,\n'
                '            "document has an active job: cancel it before reprocessing",\n'
                '        )\n',
                '')],
        test="tests.test_documents.DocumentTests.test_reprocess_conflicts_with_active_job",
    ),
    dict(
        name="F3 url content-type allowlist off",
        file="app/backend/routers/documents.py",
        edits=[('            if content_type not in URL_CONTENT_TYPES:\n'
                '                raise HTTPException(\n'
                '                    http_status.HTTP_422_UNPROCESSABLE_CONTENT,\n'
                '                    "url content type is not supported",\n'
                '                )\n',
                '            if content_type not in URL_CONTENT_TYPES:\n'
                '                pass\n')],
        test="tests.test_documents.DocumentTests.test_url_content_type_and_size_limits",
    ),
    dict(
        name="F4 url body size limit off",
        file="app/backend/routers/documents.py",
        edits=[('                if len(body) > config.MAX_UPLOAD_BYTES:\n'
                '                    raise HTTPException(\n'
                '                        http_status.HTTP_413_CONTENT_TOO_LARGE,\n'
                '                        f"url content exceeds {config.MAX_UPLOAD_MB} MB",\n'
                '                    )\n',
                '                if False:\n                    pass\n')],
        test="tests.test_documents.DocumentTests.test_url_content_type_and_size_limits",
    ),
    dict(
        name="F4 url extracted text not truncated",
        file="app/backend/routers/documents.py",
        edits=[("            )[:MAX_URL_TEXT_CHARS]\n", "            )\n")],
        test="tests.test_documents.DocumentTests.test_url_content_type_and_size_limits",
    ),
    dict(
        name="F4 early content-length middleware off",
        file="app/backend/main.py",
        edits=[("    app.add_middleware(UploadSizeLimitMiddleware)\n", "")],
        test="tests.test_documents.DocumentTests.test_content_length_rejected_before_parsing",
    ),
    dict(
        name="F4 missing yandex local copy returns 404",
        file="app/backend/routers/documents.py",
        edits=[('        raise HTTPException(\n'
                '            http_status.HTTP_409_CONFLICT,\n'
                '            "local copy is missing: downloading from the external storage "\n',
                '        raise HTTPException(\n'
                '            http_status.HTTP_404_NOT_FOUND,\n'
                '            "local copy is missing: downloading from the external storage "\n')],
        test="tests.test_documents.DocumentTests.test_yandex_without_local_copy_is_409",
    ),
    # ---------- regression sweep: earlier isolation/A3 defects must still be caught ----------
    dict(
        name="docs list drops owner filter",
        file="app/backend/routers/documents.py",
        edits=[("    query = db.query(Document).filter(Document.owner_id == user.id)\n",
                "    query = db.query(Document)\n")],
        test="tests.test_ingest_isolation.IngestIsolationTests.test_documents_isolated_between_users",
    ),
    dict(
        name="worker claim drops owner filter",
        file="app/backend/routers/worker.py",
        edits=[('.filter(Job.owner_id == token.owner_id, Job.status == "queued")',
                '.filter(Job.status == "queued")')],
        test="tests.test_worker.WorkerTests.test_owner_isolation",
    ),
    dict(
        name="yadisk settings leak raw token",
        file="app/backend/routers/settings_yadisk.py",
        edits=[("    return YadiskSettingsOut(configured=True, masked=yadisk.mask_token(raw))",
                "    return YadiskSettingsOut(configured=True, masked=raw)")],
        test="tests.test_yadisk.YadiskTests.test_settings_put_get_delete",
    ),
    dict(
        name="search drops owner scoping (all layers)",
        file="app/backend/knowledge/search.py",
        edits=[
            ("    query = db.query(Document.id, Document.tags).filter(Document.owner_id == user.id)\n",
             "    query = db.query(Document.id, Document.tags)\n"),
            ("            Chunk.owner_id == owner_id,\n            Chunk.document_id.in_(document_ids),\n",
             "            Chunk.document_id.in_(document_ids),\n"),
            ("            Chunk.owner_id == user.id,\n            Document.owner_id == user.id,\n            Chunk.id.in_(chunk_ids),\n",
             "            Chunk.id.in_(chunk_ids),\n"),
        ],
        test="tests.test_search.SearchTests.test_other_owner_sees_nothing",
    ),
    dict(
        name="dedup ignores owner",
        file="app/backend/routers/documents.py",
        edits=[(".filter_by(owner_id=owner_id, sha256=sha256)", ".filter_by(sha256=sha256)")],
        test="tests.test_ingest_isolation.IngestIsolationTests.test_dedup_and_quota_are_owner_scoped",
    ),
    dict(
        name="A3 pdf fast path always defers",
        file="app/backend/knowledge/pipeline.py",
        edits=[('    return {"defer": False, "kind": None, "reason": "pdf fast path"}',
                '    return {"defer": True, "kind": "extract", "reason": "mutated"}')],
        test="tests.test_ingest_acceptance.IngestAcceptanceTests.test_text_pdf_is_ready_and_searchable",
    ),
    dict(
        name="chunking loses overlap (old test)",
        file="app/backend/knowledge/chunking.py",
        edits=[("            target = max(1, int(current_tokens * overlap_ratio))\n"
                "            overlap: list[str] = []\n"
                "            overlap_tokens = 0\n"
                "            for previous in reversed(current):\n"
                "                previous_tokens = count_tokens(previous)\n"
                "                if overlap and overlap_tokens + previous_tokens > target:\n"
                "                    break\n"
                "                overlap.insert(0, previous)\n"
                "                overlap_tokens += previous_tokens\n"
                "                if overlap_tokens >= target:\n"
                "                    break\n"
                "            current = overlap\n"
                "            current_tokens = overlap_tokens\n",
                "            current = []\n            current_tokens = 0\n")],
        test="tests.test_chunking",
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    missed = []
    for m in MUTATIONS:
        path = MUT / m["file"]
        original = path.read_bytes()
        before = digest(path)
        text = path.read_text(encoding="utf-8")
        try:
            for old, new in m["edits"]:
                count = text.count(old)
                if count != 1:
                    raise SystemExit(f"{m['name']}: pattern found {count}x, expected 1:\n{old!r}")
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [str(PY), "-m", "unittest", m["test"]],
                cwd=str(MUT), capture_output=True, text=True, timeout=600,
            )
            caught = result.returncode != 0
            tail = [ln.strip() for ln in (result.stderr or result.stdout).splitlines()
                    if ln.strip().startswith(("FAILED", "ERROR", "AssertionError", "Ran "))][-2:]
            print(f"{'CAUGHT' if caught else 'MISSED'}  {m['name']}")
            for ln in tail:
                print(f"         {ln}")
            if not caught:
                missed.append(m["name"])
        finally:
            path.write_bytes(original)
            if digest(path) != before:
                raise SystemExit(f"restore failed: {m['file']}")
    if missed:
        print("MISSED:", missed)
        return 1
    print(f"ALL {len(MUTATIONS)} MUTATIONS CAUGHT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
