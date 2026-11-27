import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\patch-tests.py")
s = p.read_text(encoding="utf-8")

broken = """            with self.app.state.SessionLocal() as db:
                row = db.get(Message, message_id)
                row.status = "complete"
                db.commit()
            # Идемпотентно: отмена завершённого ответа — no-op, не ошибка.
            with self.app.state.SessionLocal() as db:
                row = db.get(Message, message_id)
                self.assertFalse(runtime.is_cancelled(message_id))"""
fixed = """            with self.app.state.SessionLocal() as db:
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
                self.assertEqual(db.get(Message, message_id).status, "complete")"""
assert broken in s
s = s.replace(broken, fixed)

old_imp = """from app.backend.models import (
    Chunk,
    Document,
    Event,"""
new_imp = """from app.backend.models import (
    Agent,
    Chat,
    Chunk,
    Document,
    Event,"""
assert old_imp in s
s = s.replace(old_imp, new_imp)

p.write_text(s, encoding="utf-8")
print("patch script fixed")
