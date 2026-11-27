import pathlib
p = pathlib.Path("app/backend/features/agent/service.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    """    return _stream(
        session_factory,
        user,
        agent,
        messages,
        assistant.id,
        chat.id,
    )""",
    """    return _stream(
        session_factory,
        user,
        agent,
        messages,
        assistant.id,
        chat.id,
        deep=deep,
    )""",
)

s = s.replace(
    """def _stream(
    session_factory: Callable[[], Session],
    user: User,
    agent: Agent,
    messages: list[dict[str, Any]],
    message_id: int,
    chat_id: int,
) -> Iterator[str]:""",
    """def _stream(
    session_factory: Callable[[], Session],
    user: User,
    agent: Agent,
    messages: list[dict[str, Any]],
    message_id: int,
    chat_id: int,
    *,
    deep: bool = False,
) -> Iterator[str]:""",
)

s = s.replace(
    '        yield _sse({"type": "start", "message_id": message_id})',
    '        yield _sse(\n'
    '            {"type": "start", "message_id": message_id, "meta": {"deep": deep}}\n'
    '        )',
)

s = s.replace(
    """                for event in runtime.events(
                    gen_db,
                    gen_user,
                    gen_agent,
                    messages,
                    message_id=message_id,
                    chat_id=chat_id,
                ):""",
    """                for event in runtime.events(
                    gen_db,
                    gen_user,
                    gen_agent,
                    messages,
                    message_id=message_id,
                    chat_id=chat_id,
                    deep=deep,
                ):""",
)

s = s.replace(
    """    if message.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="message is not running",
        )
    runtime.cancel(message_id)""",
    """    # Идемпотентно: повторная отмена (и отмена уже завершённого ответа) —
    # успешный no-op, клиенту не нужно различать гонки.
    if message.status != "running":
        return
    runtime.cancel(message_id)""",
)

p.write_text(s, encoding="utf-8")
print("service patched")
