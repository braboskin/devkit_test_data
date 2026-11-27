import pathlib

chat = pathlib.Path("app/backend/features/agent/chat.py")
s = chat.read_text(encoding="utf-8")

s = s.replace(
    """MAX_TOOL_ROUNDS = 6
CITATION_TEXT = 300""",
    """MAX_TOOL_ROUNDS = 6
CITATION_TEXT = 300
# «Глубокий анализ»: вдвое больше фрагментов в поисковом инструменте.
DEEP_SEARCH_LIMIT = 10""",
)

s = s.replace(
    """def _run_tool(
    db: Session,
    user: User,
    agent: Agent,
    name: str,
    arguments: dict[str, Any],
    citations: dict[int | None, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    \"\"\"Выполнить инструмент; вернуть результат и события proposal/citation.\"\"\"
    try:
        result = tools.execute(db, user, agent, name, arguments)""",
    """def _run_tool(
    db: Session,
    user: User,
    agent: Agent,
    name: str,
    arguments: dict[str, Any],
    citations: dict[int | None, dict[str, Any]],
    *,
    deep: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    \"\"\"Выполнить инструмент; вернуть результат и события proposal/citation.\"\"\"
    try:
        result = tools.execute(
            db,
            user,
            agent,
            name,
            arguments,
            search_limit=DEEP_SEARCH_LIMIT if deep else None,
        )""",
)

s = s.replace(
    """def _tool_messages(
    db: Session,
    user: User,
    agent: Agent,
    assistant_calls: list[dict[str, Any]],
    citations: dict[int | None, dict[str, Any]],
) -> Iterator[dict[str, Any]]:""",
    """def _tool_messages(
    db: Session,
    user: User,
    agent: Agent,
    assistant_calls: list[dict[str, Any]],
    citations: dict[int | None, dict[str, Any]],
    *,
    deep: bool,
) -> Iterator[dict[str, Any]]:""",
)

s = s.replace(
    """        result, emitted = _run_tool(
            db,
            user,
            agent,
            call["function"]["name"],
            arguments,
            citations,
        )""",
    """        result, emitted = _run_tool(
            db,
            user,
            agent,
            call["function"]["name"],
            arguments,
            citations,
            deep=deep,
        )""",
)

s = s.replace(
    """    message_id: int | None,
    finish: bool,
    text_box: list[str],
) -> Iterator[dict[str, Any]]:""",
    """    message_id: int | None,
    finish: bool,
    text_box: list[str],
    deep: bool = False,
) -> Iterator[dict[str, Any]]:""",
)

s = s.replace(
    """        for event in _tool_messages(db, user, agent, assistant_calls, citations):""",
    """        for event in _tool_messages(
            db, user, agent, assistant_calls, citations, deep=deep
        ):""",
)

s = s.replace(
    """    message_id: int | None = None,
    chat_id: int | None = None,
) -> Iterator[dict[str, Any]]:
    \"\"\"События ответа: `delta`, `replace`, `citation`, `proposal`, `usage`,
    `done`, `cancelled`.\"\"\"""",
    """    message_id: int | None = None,
    chat_id: int | None = None,
    deep: bool = False,
) -> Iterator[dict[str, Any]]:
    \"\"\"События ответа: `delta`, `replace`, `citation`, `proposal`, `usage`,
    `done`, `cancelled`.\"\"\"""",
)

s = s.replace(
    """            message_id=message_id,
            chat_id=chat_id,
        )
        return
    yield from _stream_turn(""",
    """            message_id=message_id,
            chat_id=chat_id,
            deep=deep,
        )
        return
    yield from _stream_turn(""",
)

s = s.replace(
    """        finish=True,
        text_box=[],
    )""",
    """        finish=True,
        text_box=[],
        deep=deep,
    )""",
)

s = s.replace(
    """    message_id: int | None,
    chat_id: int | None,
) -> Iterator[dict[str, Any]]:
    \"\"\"Черновик стримится сразу → «Критик» → «Редактор» → `replace` (A16).\"\"\"""",
    """    message_id: int | None,
    chat_id: int | None,
    deep: bool,
) -> Iterator[dict[str, Any]]:
    \"\"\"Черновик стримится сразу → «Критик» → «Редактор» → `replace` (A16).\"\"\"""",
)

s = s.replace(
    """        finish=False,
        text_box=draft_box,
    )""",
    """        finish=False,
        text_box=draft_box,
        deep=deep,
    )""",
)

chat.write_text(s, encoding="utf-8")

tools = pathlib.Path("app/backend/features/agent/tools.py")
t = tools.read_text(encoding="utf-8")
t = t.replace(
    """def execute(
    db: Session, user: User, agent: Agent, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    \"\"\"Выполнить инструмент; ошибка домена — `ValueError` (в результат модели).\"\"\"
    allowed = {tool["function"]["name"] for tool in definitions(agent)}
    if name not in allowed:
        raise ValueError(f"tool is not available: {name}")
    handler = _READ_HANDLERS.get(name)
    if handler is not None:
        return handler(db, user, agent, args)""",
    """def execute(
    db: Session,
    user: User,
    agent: Agent,
    name: str,
    args: dict[str, Any],
    *,
    search_limit: int | None = None,
) -> dict[str, Any]:
    \"\"\"Выполнить инструмент; ошибка домена — `ValueError` (в результат модели).

    `search_limit` поднимает лимит `search`, когда модель его не задала
    («Глубокий анализ»); явный лимит модели не переопределяется.
    \"\"\"
    allowed = {tool["function"]["name"] for tool in definitions(agent)}
    if name not in allowed:
        raise ValueError(f"tool is not available: {name}")
    handler = _READ_HANDLERS.get(name)
    if handler is not None:
        if name == "search" and search_limit is not None and "limit" not in args:
            args = {**args, "limit": search_limit}
        return handler(db, user, agent, args)""",
)
tools.write_text(t, encoding="utf-8")
print("chat and tools patched")
