"""E2E-проверка MCP: search_kb → get_document → logs."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "scripts" / "mcp_server.py"
LOG = ROOT / "logs" / "queries.jsonl"


def parse_result(result) -> dict:
    text = result.content[0].text
    return json.loads(text)


async def main() -> None:
    env = {
        **os.environ,
        "HF_HOME": str(ROOT / ".cache" / "huggingface"),
        "ATLAS_LOG": str(LOG),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            print(f"tools: {names}")
            if "search_kb" not in names or "get_document" not in names:
                raise SystemExit("MCP tools missing")

            search_result = await session.call_tool(
                "search_kb", {"query": "ремонт", "limit": 3}
            )
            search_data = parse_result(search_result)
            if not search_data.get("ok") or not search_data.get("results"):
                raise SystemExit(f"search failed: {search_data}")
            top = search_data["results"][0]
            print(
                f"top: {top['doc_id']} — {top['title']} "
                f"(score={top['score']:.4f})"
            )

            document_result = await session.call_tool(
                "get_document",
                {"doc_id": top["doc_id"], "max_chars": 3000},
            )
            document = parse_result(document_result)
            if not document.get("ok"):
                raise SystemExit(f"get_document failed: {document}")
            print(
                f"document: {document['doc_id']} — {document['title']} "
                f"(truncated={document['truncated']})"
            )

            warm_result = await session.call_tool(
                "search_kb", {"query": "инвестиции", "limit": 2}
            )
            warm_data = parse_result(warm_result)
            print(f"warm search: {len(warm_data.get('results', []))} results")

            lines = (
                LOG.read_text(encoding="utf-8").splitlines()
                if LOG.exists()
                else []
            )
            print(f"log lines: {len(lines)}")
            if len(lines) < 2:
                raise SystemExit("query log not written")

            print("E2E OK")


if __name__ == "__main__":
    asyncio.run(main())
