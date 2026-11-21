"""MCP-сервер Atlas: search_kb и get_document."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mcp.server.mcpserver import MCPServer  # noqa: E402

import retrieval  # noqa: E402

mcp = MCPServer("atlas")


@mcp.tool()
def search_kb(query: str, limit: int = 5, rerank: bool = False) -> dict:
    """Найти фрагменты знаний Atlas по запросу и вернуть источники."""
    started = time.perf_counter()
    try:
        results = retrieval.search(query, limit=limit, rerank=rerank)
        latency_ms = int((time.perf_counter() - started) * 1000)
        retrieval.log_event(
            "search_kb",
            {"query": query, "limit": limit, "rerank": rerank},
            len(results),
            latency_ms,
        )
        return {"ok": True, "query": query, "results": results}
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        retrieval.log_event(
            "search_kb",
            {"query": query, "limit": limit, "rerank": rerank},
            0,
            latency_ms,
            status="error",
            error=str(exc),
        )
        return {"ok": False, "query": query, "error": str(exc)}


@mcp.tool()
def get_document(doc_id: str, max_chars: int = 20000) -> dict:
    """Прочитать документ по doc_id с метаданными и хешем."""
    started = time.perf_counter()
    try:
        result = retrieval.get_document(doc_id, max_chars=max_chars)
        latency_ms = int((time.perf_counter() - started) * 1000)
        retrieval.log_event(
            "get_document",
            {"doc_id": doc_id, "max_chars": max_chars},
            1 if result.get("ok") else 0,
            latency_ms,
            status="ok" if result.get("ok") else "error",
            error=None if result.get("ok") else result.get("error"),
        )
        return result
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        retrieval.log_event(
            "get_document",
            {"doc_id": doc_id, "max_chars": max_chars},
            0,
            latency_ms,
            status="error",
            error=str(exc),
        )
        return {"ok": False, "doc_id": doc_id, "error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
