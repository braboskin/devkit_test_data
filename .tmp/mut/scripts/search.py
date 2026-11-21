"""CLI поиска по Atlas: BGE-M3 dense + sparse, RRF."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from retrieval import DEFAULT_COLLECTION, DEFAULT_QDRANT, search  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Поиск по Atlas")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = search(
        args.query,
        limit=args.limit,
        collection=args.collection,
        qdrant=args.qdrant,
        rerank=args.rerank,
        candidate_limit=args.candidate_limit,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for index, result in enumerate(results, 1):
            print(
                f"{index}. {result['title']} — "
                f"{result['doc_id']}#{result['chunk_index']}"
            )
            print(
                f"   score={result['score']:.4f}  "
                f"tokens={result['token_count']}"
                + (
                    f"  rerank={result['rerank_score']:.4f}"
                    if "rerank_score" in result
                    else ""
                )
            )
            text = " ".join(result["text"].split())
            print(f"   {text[:320]}")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
