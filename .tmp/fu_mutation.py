"""WS-C: ручная мутационная проверка acceptance-тестов (репозиторий не трогаем).

Копирует `app/` и `tests/` кандидата в `.tmp/mut-fu`, вносит дефект в копию,
запускает целевой тест: контроль — зелёный, мутация — красный.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(r"X:\devkit_instance\testproject\repo\atlas")
MUT = Path(r"X:\devkit_instance\testproject\.tmp\mut-fu")
PY = REPO / ".venv" / "Scripts" / "python.exe"
TEST = "tests.test_followup_acceptance"

MUTATIONS = (
    (
        "reindex: owner-фильтр убран",
        "app/backend/routers/documents.py",
        '    document = get_owned_or_404(db, Document, document_id, user)\n'
        "    try:\n"
        "        index_document(db, document)",
        '    document = db.get(Document, document_id)\n'
        "    try:\n"
        "        index_document(db, document)",
        f"{TEST}.FollowUpAcceptanceTests.test_isolation_between_owners",
    ),
    (
        "claim: owner-фильтр убран",
        "app/backend/routers/worker.py",
        '                Job.owner_id == token.owner_id,\n'
        '                Job.status == "queued",',
        '                Job.status == "queued",',
        f"{TEST}.FollowUpAcceptanceTests.test_isolation_between_owners "
        f"{TEST}.FollowUpAcceptanceTests.test_f12_different_owners_claim_their_own_jobs",
    ),
    (
        "F7: гонка дедупа не перехватывается",
        "app/backend/routers/documents.py",
        "        raced = _duplicate_after_race(\n"
        "            db, owner_id, sha256, lambda: tmp.unlink(missing_ok=True)\n"
        "        )\n"
        "        if raced is None:\n"
        "            raise\n"
        "        return raced",
        "        raced = None\n"
        "        if raced is None:\n"
        "            raise\n"
        "        return raced",
        f"{TEST}.FollowUpAcceptanceTests.test_f7_duplicate_race_returns_existing",
    ),
    (
        "F9: сбой индексации не пишется в error",
        "app/backend/routers/documents.py",
        '            current.error = "indexing failed"',
        "            current.error = None",
        f"{TEST}.FollowUpAcceptanceTests.test_f9_index_failure_visible_and_reindex_recovers",
    ),
)


def fresh_copy() -> None:
    if MUT.exists():
        shutil.rmtree(MUT)
    MUT.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "app", MUT / "app", ignore=ignore)
    shutil.copytree(REPO / "tests", MUT / "tests", ignore=ignore)


def run(targets: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PY), "-m", "unittest", *targets.split()],
        cwd=str(MUT),
        capture_output=True,
        text=True,
        timeout=600,
    )


def tail(result: subprocess.CompletedProcess) -> str:
    lines = [
        line.strip()
        for line in (result.stderr + result.stdout).splitlines()
        if line.strip().startswith(("FAIL:", "ERROR:", "Ran ", "OK", "FAILED"))
    ]
    return " | ".join(lines[-3:])


def main() -> int:
    problems = 0
    fresh_copy()
    for name, rel, old, new, targets in MUTATIONS:
        # Контроль на этой же копии до мутации.
        fresh_copy()
        control = run(targets)
        status = "PASS" if control.returncode == 0 else "FAIL"
        print(f"{name}: control {status}")
        if control.returncode != 0:
            print("  ", tail(control))
            problems += 1
            continue

        path = MUT / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"  мутация не найдена ровно один раз в {rel}")
            problems += 1
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        mutated = run(targets)
        caught = mutated.returncode != 0
        print(f"  mutated: {'CAUGHT' if caught else 'MISSED'} — {tail(mutated)}")
        if not caught:
            problems += 1
    fresh_copy()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
