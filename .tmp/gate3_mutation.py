"""Independent mutation check for the F4 test isolation fix (candidate untouched)."""
import hashlib
import subprocess
import sys
from pathlib import Path

MUT = Path(r"X:\devkit_projects\projects\atlas\.tmp\mut3")
PY = Path(r"X:\devkit_projects\projects\atlas\repo\atlas\.venv\Scripts\python.exe")
TARGET = "tests.test_documents.DocumentTests.test_url_content_type_and_size_limits"
FILE = MUT / "app/backend/routers/documents.py"
OLD = """                if len(body) > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        http_status.HTTP_413_CONTENT_TOO_LARGE,
                        f"url content exceeds {config.MAX_UPLOAD_MB} MB",
                    )
"""
NEW = "                if False:\n                    pass\n"


def run() -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PY), "-m", "unittest", TARGET],
        cwd=str(MUT), capture_output=True, text=True, timeout=300,
    )


def main() -> int:
    original = FILE.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    text = FILE.read_text(encoding="utf-8")
    if text.count(OLD) != 1:
        raise SystemExit("stream-limit block not found exactly once")

    control = run()
    print(f"control (intact):        exit={control.returncode} "
          f"{'PASS' if control.returncode == 0 else 'FAIL'}")
    if control.returncode != 0:
        print(control.stderr[-1500:])
        return 2

    FILE.write_text(text.replace(OLD, NEW), encoding="utf-8")
    try:
        mutated = run()
    finally:
        FILE.write_bytes(original)
        assert hashlib.sha256(FILE.read_bytes()).hexdigest() == before
    tail = [ln.strip() for ln in mutated.stderr.splitlines()
            if ln.strip().startswith(("FAILED", "AssertionError", "Ran "))][-3:]
    print(f"mutated (limit removed): exit={mutated.returncode} "
          f"{'CAUGHT' if mutated.returncode != 0 else 'MISSED'}")
    for ln in tail:
        print("  ", ln)
    return 0 if mutated.returncode != 0 else 1


if __name__ == "__main__":
    sys.exit(main())
