"""Чанкинг + BGE-M3 (dense+sparse) + Qdrant."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "huggingface"
CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from FlagEmbedding import BGEM3FlagModel  # noqa: E402
from qdrant_client import QdrantClient, models  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

from chunking import chunk_text  # noqa: E402

MODEL_NAME = "BAAI/bge-m3"
DEFAULT_COLLECTION = "kb_chunks"
DEFAULT_QDRANT = "http://127.0.0.1:6333"
DENSE_SIZE = 1024

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def to_sparse(weights: dict) -> models.SparseVector:
    items = sorted(
        (int(key), float(value))
        for key, value in weights.items()
        if float(value) > 0
    )
    if not items:
        raise ValueError("empty sparse vector")
    return models.SparseVector(
        indices=[index for index, _ in items],
        values=[value for _, value in items],
    )


def load_chunks(
    processed: Path, meta: Path, tokenizer
) -> tuple[int, list[dict], list[dict], list[dict]]:
    def count_tokens(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    docs = 0
    chunks: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    for path in sorted(processed.glob("*.md")):
        doc_id = path.stem
        meta_path = meta / f"{doc_id}.json"
        if not meta_path.exists():
            errors.append({"doc_id": doc_id, "reason": "metadata not found"})
            continue
        try:
            record = json.loads(meta_path.read_text(encoding="utf-8"))
            text = path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"doc_id": doc_id, "reason": str(exc)})
            continue

        triage = record.get("triage") or {}
        policy = triage.get("index_policy", "full")
        if policy in {"skip", "metadata_only"}:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "policy": policy,
                    "reason": triage.get("reason", ""),
                }
            )
            continue

        source_text = text
        if policy == "summary":
            source_text = triage.get("summary") or text[:1500]

        doc_chunks = chunk_text(source_text, count_tokens)
        docs += 1
        for index, chunk in enumerate(doc_chunks):
            chunks.append(
                {
                    "chunk_id": f"{doc_id}:{index:03d}",
                    "doc_id": doc_id,
                    "chunk_index": index,
                    "text": chunk["text"],
                    "token_count": chunk["token_count"],
                    "title": record.get("title", doc_id),
                    "source_path": record.get("source_path", ""),
                    "tags": record.get("tags", []),
                    "content_hash": record.get("content_hash", ""),
                    "type": triage.get("type"),
                    "sphere": triage.get("sphere"),
                    "project": triage.get("project"),
                    "index_policy": policy,
                    "sensitive": triage.get("sensitive"),
                    "summary": triage.get("summary"),
                    "language": triage.get("language"),
                }
            )

    return docs, chunks, skipped, errors


def ensure_collection(client: QdrantClient, name: str, recreate: bool) -> None:
    existing = {collection.name for collection in client.get_collections().collections}
    if recreate and name in existing:
        client.delete_collection(collection_name=name)
        existing.discard(name)
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": models.VectorParams(
                    size=DENSE_SIZE,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Индексация Atlas в Qdrant")
    parser.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--meta", type=Path, default=ROOT / "data" / "meta")
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args(argv)

    if not args.processed.exists():
        parser.error(f"processed not found: {args.processed}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = BGEM3FlagModel(MODEL_NAME, use_fp16=False)

    docs, chunks, skipped, errors = load_chunks(
        args.processed, args.meta, tokenizer
    )
    skipped_by_policy = dict(Counter(item["policy"] for item in skipped))
    if not chunks:
        print(
            json.dumps(
                {
                    "docs": docs,
                    "chunks": 0,
                    "skipped": len(skipped),
                    "skipped_by_policy": skipped_by_policy,
                    "errors": errors,
                },
                ensure_ascii=False,
            )
        )
        return 0 if docs or skipped else 1

    client = QdrantClient(url=args.qdrant)
    ensure_collection(client, args.collection, args.recreate)

    points = 0
    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start : start + args.batch_size]
        output = model.encode(
            [chunk["text"] for chunk in batch],
            batch_size=len(batch),
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        structs: list[models.PointStruct] = []
        for chunk, dense, weights in zip(
            batch, output["dense_vecs"], output["lexical_weights"]
        ):
            structs.append(
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
                    vector={
                        "dense": dense.tolist(),
                        "sparse": to_sparse(weights),
                    },
                    payload=chunk,
                )
            )
        client.upsert(
            collection_name=args.collection,
            points=structs,
            wait=True,
        )
        points += len(structs)

    summary = {
        "docs": docs,
        "chunks": len(chunks),
        "points": points,
        "skipped": len(skipped),
        "skipped_by_policy": skipped_by_policy,
        "collection": args.collection,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if points else 1


if __name__ == "__main__":
    raise SystemExit(main())
