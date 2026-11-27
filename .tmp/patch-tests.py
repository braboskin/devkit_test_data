import pathlib

chat = pathlib.Path("tests/test_agent_chat.py")
s = chat.read_text(encoding="utf-8")

s = s.replace(
    "from app.backend.features.agent import chat as runtime",
    "from app.backend.features.agent import chat as runtime\nfrom app.backend.features.agent.context import DEEP_INSTRUCTION",
)

s = s.replace(
    """            self._document(db, bob.id, "Боб", bob_sphere.id, "анализы боба")""",
    """            self._document(db, bob.id, "Боб", bob_sphere.id, "анализы боба")
            self.bob_doc_id = self._last_doc(db, bob.id)""",
)

s = s.replace(
    """    def _send(self, client: TestClient, chat_id: int, text: str) -> httpx.Response:
        return client.post(f"/api/chats/{chat_id}/messages", json={"content": text})""",
    """    def _send(
        self, client: TestClient, chat_id: int, text: str, **extra: object
    ) -> httpx.Response:
        return client.post(
            f"/api/chats/{chat_id}/messages",
            json={"content": text, **extra},
        )""",
)

s = s.replace(
    """            with self.app.state.SessionLocal() as db:
                row = db.get(Message, message_id)
                row.status = "complete"
                db.commit()
            self.assertEqual(
                client.post(
                    f"/api/chats/{chat_id}/messages/{message_id}/cancel"
                ).status_code,
                409,
            )""",
    """            with self.app.state.SessionLocal() as db:
                row = db.get(Message, message_id)
                row.status = "complete"
                db.commit()
            # Идемпотентно: отмена завершённого ответа — no-op, не ошибка.
            self.assertEqual(
                client.post(
                    f"/api/chats/{chat_id}/messages/{message_id}/cancel"
                ).status_code,
                204,
            )
            with self.app.state.SessionLocal() as db:
                self.assertEqual(db.get(Message, message_id).status, "complete")""",
)

new_tests = '''
    def _extra_chunks(self, count: int) -> None:
        with self.app.state.SessionLocal() as db:
            for index in range(count):
                db.add(
                    Chunk(
                        document_id=self.work_doc_id,
                        owner_id=self.alice_id,
                        ord=index + 1,
                        text=f"отчёт номер {index} выручка",
                    )
                )
            db.commit()

    @staticmethod
    def _tool_result_count(body: dict) -> int:
        tool_messages = [
            item for item in body["messages"] if item.get("role") == "tool"
        ]
        assert tool_messages, body["messages"]
        return len(json.loads(tool_messages[-1]["content"])["results"])

    def test_deep_doubles_context_and_adds_instruction(self) -> None:
        self._extra_chunks(11)

        def handler(seen: list[dict]):
            def respond(request: httpx.Request) -> httpx.Response:
                body = json.loads(request.content)
                seen.append(body)
                if any(item.get("role") == "tool" for item in body["messages"]):
                    return _streaming([_chunk("Подробный ответ.")])
                return _streaming(
                    [
                        _tool_call("search", {"query": "отчёт"}),
                        _chunk(None, finish_reason="tool_calls"),
                    ]
                )

            return respond

        normal: list[dict] = []
        deep: list[dict] = []
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            self._save_key(client)
            chat_id = self._chat(client)
            with mock.patch.object(
                llm, "TRANSPORT", httpx.MockTransport(handler(normal))
            ):
                self._send(client, chat_id, "Что по отчётам?")
            with mock.patch.object(llm, "TRANSPORT", httpx.MockTransport(handler(deep))):
                response = self._send(
                    client, chat_id, "Что по отчётам подробно?", deep=True
                )

        self.assertEqual(self._tool_result_count(normal[-1]), 5)
        self.assertEqual(self._tool_result_count(deep[-1]), 10)
        normal_system = next(
            item for item in normal[0]["messages"] if item.get("role") == "system"
        )
        deep_system = next(
            item for item in deep[0]["messages"] if item.get("role") == "system"
        )
        self.assertNotIn(DEEP_INSTRUCTION, normal_system["content"])
        self.assertIn(DEEP_INSTRUCTION, deep_system["content"])
        self.assertIn('"deep": true', response.text)

    def test_attached_documents_context_and_validation(self) -> None:
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return _streaming([_chunk("ответ по документу")])

        with TestClient(self.app) as client:
            self._login(client, ALICE)
            self._save_key(client)
            chat_id = self._chat(client)
            with mock.patch.object(
                llm, "TRANSPORT", httpx.MockTransport(handler)
            ):
                response = self._send(
                    client,
                    chat_id,
                    "О чём отчёт?",
                    document_ids=[self.work_doc_id],
                )
            self.assertEqual(response.status_code, 200, response.text)

            for document_ids in ([self.bob_doc_id], [999_999]):
                rejected = client.post(
                    f"/api/chats/{chat_id}/messages",
                    json={"content": "чужой документ", "document_ids": document_ids},
                )
                self.assertEqual(rejected.status_code, 422, rejected.text)
                self.assertNotIn("Боб", rejected.text)

            too_many = client.post(
                f"/api/chats/{chat_id}/messages",
                json={"content": "много", "document_ids": list(range(1, 12))},
            )
            self.assertEqual(too_many.status_code, 422, too_many.text)

        messages = seen[0]["messages"]
        attached = [
            item
            for item in messages
            if item.get("role") == "system" and "приоритетный контекст" in item["content"]
        ]
        self.assertTrue(attached, messages)
        self.assertIn("выручка отчёт квартал", attached[0]["content"])
        user_index = next(
            index
            for index, item in enumerate(messages)
            if item.get("role") == "user" and item.get("content") == "О чём отчёт?"
        )
        self.assertLess(messages.index(attached[0]), user_index)
'''

marker = '\n\nif __name__ == "__main__":'
assert marker in s
s = s.replace(marker, new_tests + marker, 1)

chat.write_text(s, encoding="utf-8")
print("chat tests patched")

iso = pathlib.Path("tests/test_isolation.py")
t = iso.read_text(encoding="utf-8")

t = t.replace(
    """from app.backend.models import (
    Event,""",
    """from app.backend.models import (
    Agent,
    Chat,
    Chunk,
    Document,
    Event,""",
)

t = t.replace(
    '            ("POST", "/api/chats/{chat_id}/messages"): {"content": "привет"},',
    '            ("POST", "/api/chats/{chat_id}/messages"): {\n'
    '                "content": "привет",\n'
    '                "deep": True,\n'
    '                "document_ids": [],\n'
    '            },',
)

iso_test = '''
    def test_chat_message_contract_and_foreign_documents(self) -> None:
        """Новый контракт `MessageIn` и изоляция вложений между владельцами."""
        properties = self.app.openapi()["components"]["schemas"]["MessageIn"][
            "properties"
        ]
        self.assertLessEqual({"content", "deep", "document_ids"}, set(properties))

        with self.app.state.SessionLocal() as db:
            document = Document(
                owner_id=self.alice_id,
                title="Секреты alice",
                status="ready",
                source_type="file",
            )
            db.add(document)
            db.flush()
            db.add(
                Chunk(
                    document_id=document.id,
                    owner_id=self.alice_id,
                    ord=0,
                    text="секрет alice",
                )
            )
            db.commit()
            alice_document_id = document.id
            alice_agent = Agent(owner_id=self.alice_id, name="Агент alice")
            db.add(alice_agent)
            db.flush()
            alice_chat = Chat(
                owner_id=self.alice_id, agent_id=alice_agent.id, title="Чат"
            )
            db.add(alice_chat)
            db.commit()
            alice_chat_id = alice_chat.id

        bob_agent = self._ok(self.bob.post("/api/agents", json={"name": "Боб"}), 201)
        bob_chat = self._ok(
            self.bob.post("/api/chats", params={"agent_id": bob_agent["id"]}), 201
        )
        rejected = self.bob.post(
            f"/api/chats/{bob_chat['id']}/messages",
            json={"content": "привет", "document_ids": [alice_document_id]},
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertNotIn("Секреты alice", rejected.text)
        with self.app.state.SessionLocal() as db:
            self.assertEqual(
                db.query(Message).filter_by(chat_id=bob_chat["id"]).count(), 0
            )

        # Чужой чат по-прежнему 404 — id утёкшего документа не расширяет доступ.
        foreign = self.bob.post(
            f"/api/chats/{alice_chat_id}/messages",
            json={"content": "привет", "document_ids": [alice_document_id]},
        )
        self.assertEqual(foreign.status_code, 404, foreign.text)
'''

anchor = """
    def test_foreign_filters_and_payload_ids_404(self) -> None:"""
assert anchor in t
t = t.replace(anchor, iso_test + anchor, 1)

iso.write_text(t, encoding="utf-8")
print("isolation tests patched")
