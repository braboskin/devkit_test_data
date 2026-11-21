"""Eval Atlas: Recall@5, MRR и latency для baseline и rerank."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from retrieval import search  # noqa: E402

DEFAULT_QA = ROOT / "eval" / "qa.local.json"
EXAMPLE_QA = ROOT / "eval" / "qa.example.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil((percent / 100) * len(ordered)) - 1
    return ordered[max(0, min(len(ordered) - 1, index))]


def recall_at_k(results: list[dict], expected: set[str], k: int = 5) -> float:
    return 1.0 if any(
        result.get("doc_id") in expected for result in results[:k]
    ) else 0.0


def reciprocal_rank(results: list[dict], expected: set[str]) -> float:
    for rank, result in enumerate(results, 1):
        if result.get("doc_id") in expected:
            return 1.0 / rank
    return 0.0


def load_questions(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions") or []
    return [
        question
        for question in questions
        if question.get("question") and question.get("expected_doc_ids")
    ]


def evaluate(
    questions: list[dict],
    rerank: bool,
    limit: int = 5,
    candidate_limit: int = 20,
    warmup: int = 1,
) -> dict:
    if warmup and questions:
        search(
            questions[0]["question"],
            limit=limit,
            rerank=rerank,
            candidate_limit=candidate_limit,
        )

    rows = []
    for question in questions:
        expected = set(question.get("expected_doc_ids") or [])
        started = time.perf_counter()
        results = search(
            question["question"],
            limit=limit,
            rerank=rerank,
            candidate_limit=candidate_limit,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        rank = next(
            (
                position
                for position, result in enumerate(results, 1)
                if result.get("doc_id") in expected
            ),
            None,
        )
        rows.append(
            {
                "id": question.get("id"),
                "question": question["question"],
                "expected": sorted(expected),
                "rank": rank,
                "recall": 1.0 if rank and rank <= limit else 0.0,
                "mrr": 1.0 / rank if rank else 0.0,
                "latency_ms": latency_ms,
                "top": [result.get("doc_id") for result in results],
            }
        )

    latencies = [row["latency_ms"] for row in rows]
    metrics = {
        "recall_at_k": (
            sum(row["recall"] for row in rows) / len(rows) if rows else 0.0
        ),
        "mrr": sum(row["mrr"] for row in rows) / len(rows) if rows else 0.0,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
    }
    return {
        "rerank": rerank,
        "limit": limit,
        "candidate_limit": candidate_limit,
        "questions": len(rows),
        "metrics": metrics,
        "rows": rows,
    }


def print_metrics(label: str, result: dict) -> None:
    metrics = result["metrics"]
    print(
        f"{label:10} recall@{result['limit']}={metrics['recall_at_k']:.3f}  "
        f"mrr={metrics['mrr']:.3f}  "
        f"p50={metrics['p50_ms']}ms  p95={metrics['p95_ms']}ms"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Eval Atlas")
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    qa_path = args.qa
    if not qa_path.exists() and qa_path == DEFAULT_QA:
        qa_path = EXAMPLE_QA
    if not qa_path.exists():
        parser.error(f"qa not found: {qa_path}")

    questions = load_questions(qa_path)
    if not questions:
        parser.error(f"no questions in {qa_path}")

    if args.compare:
        baseline = evaluate(
            questions,
            rerank=False,
            limit=args.limit,
            candidate_limit=args.candidate_limit,
            warmup=args.warmup,
        )
        reranked = evaluate(
            questions,
            rerank=True,
            limit=args.limit,
            candidate_limit=args.candidate_limit,
            warmup=args.warmup,
        )
        report = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "qa": str(qa_path),
            "baseline": baseline,
            "rerank": reranked,
        }
        print_metrics("baseline", baseline)
        print_metrics("rerank", reranked)
        results = [baseline, reranked]
    else:
        result = evaluate(
            questions,
            rerank=args.rerank,
            limit=args.limit,
            candidate_limit=args.candidate_limit,
            warmup=args.warmup,
        )
        report = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "qa": str(qa_path),
            "result": result,
        }
        print_metrics("rerank" if args.rerank else "baseline", result)
        results = [result]

    if args.verbose:
        for result in results:
            label = "rerank" if result["rerank"] else "baseline"
            for row in result["rows"]:
                print(f"{label} {row['id']}: rank={row['rank']} {row['latency_ms']}ms")

    report_path = args.report or (
        ROOT
        / "eval"
        / "reports"
        / f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
