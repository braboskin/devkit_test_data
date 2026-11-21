"""Воркер ПК Atlas: claim → скачать оригинал → извлечь текст → complete/fail.

Токен выдаётся в UI (Настройки → воркер) и передаётся через окружение:

    $env:ATLAS_WORKER_TOKEN = "..."
    .venv\\Scripts\\python.exe scripts\\worker.py --once
    .venv\\Scripts\\python.exe scripts\\worker.py --interval 10

`ATLAS_BASE_URL` — адрес сервера (default `http://127.0.0.1:8000`).
Логи не содержат токен и текст документов.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.backend.knowledge.extract import extract_file  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_INTERVAL = 10.0
TIMEOUT_SECONDS = 120.0


def log(message: str) -> None:
    print(message, flush=True)


def _fail(client: httpx.Client, job_id: int, message: str) -> None:
    try:
        client.post(f"/api/worker/jobs/{job_id}/fail", json={"error": message})
    except httpx.HTTPError as exc:
        log(f"job {job_id}: fail report lost ({exc.__class__.__name__})")


def process_once(client: httpx.Client) -> bool:
    """Обработать одно задание. True — задание было, False — очередь пуста."""
    response = client.post("/api/worker/claim")
    if response.status_code == 204:
        return False
    if response.status_code == 401:
        raise SystemExit("atlas worker: worker token rejected")
    response.raise_for_status()
    claimed = response.json()
    job_id = claimed["job"]["id"]
    document = claimed["document"]
    suffix = Path(document.get("storage_ref") or "").suffix.lower()
    log(f"job {job_id}: claimed document {document['id']}")

    try:
        original = client.get(f"/api/worker/jobs/{job_id}/file")
        original.raise_for_status()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"document{suffix}"
            path.write_bytes(original.content)
            extracted = extract_file(path, suffix or None)

        text = extracted.get("text") or ""
        if not text.strip():
            _fail(client, job_id, "empty text")
            log(f"job {job_id}: failed (empty text)")
            return True

        completed = client.post(
            f"/api/worker/jobs/{job_id}/complete",
            json={
                "text": text,
                "pages": extracted.get("pages"),
                "engine": extracted.get("engine"),
                "quality": extracted.get("quality"),
            },
        )
        if completed.status_code in (404, 409):
            # Задание отменили или оно уже завершено — результат не нужен.
            log(f"job {job_id}: skipped ({completed.status_code})")
            return True
        completed.raise_for_status()
        log(f"job {job_id}: done, {len(text)} chars")
    except Exception as exc:  # noqa: BLE001 — сбой обработки уходит в fail
        _fail(client, job_id, f"{exc.__class__.__name__}: {exc}")
        log(f"job {job_id}: failed ({exc.__class__.__name__})")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Atlas PC worker: забирает задания и распознаёт оригиналы."
    )
    parser.add_argument(
        "--once", action="store_true", help="обработать не более одного задания и выйти"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"пауза между опросами пустой очереди, сек (default {DEFAULT_INTERVAL:g})",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("ATLAS_WORKER_TOKEN", "").strip()
    if not token:
        print("atlas worker: ATLAS_WORKER_TOKEN is required", file=sys.stderr)
        return 2
    base_url = os.environ.get("ATLAS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(
        base_url=base_url, headers=headers, timeout=TIMEOUT_SECONDS
    ) as client:
        if args.once:
            try:
                process_once(client)
            except SystemExit:
                raise
            except httpx.HTTPError as exc:
                print(
                    f"atlas worker: {exc.__class__.__name__}: {exc}",
                    file=sys.stderr,
                )
                return 1
            return 0

        log("atlas worker: polling")
        while True:
            try:
                worked = process_once(client)
            except SystemExit:
                raise
            except httpx.HTTPError as exc:
                log(f"poll failed: {exc.__class__.__name__}")
                worked = False
            if not worked:
                time.sleep(max(args.interval, 0))


if __name__ == "__main__":
    raise SystemExit(main())
