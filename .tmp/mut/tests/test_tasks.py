"""FR-8 / A5: задачи, подзадачи, зависимости, RRULE, фильтры, люди, изоляция."""
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Person, Project, Sphere, Task, User, utcnow

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}


class TasksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{(Path(self.tmp.name) / 'test.db').as_posix()}"
        self.app = create_app(self.url)
        self.engine = self.app.state.engine
        Base.metadata.create_all(self.engine)

        with self.app.state.SessionLocal() as db:
            alice = User(
                username=ALICE["username"],
                password_hash=hash_password(ALICE["password"]),
            )
            bob = User(
                username=BOB["username"],
                password_hash=hash_password(BOB["password"]),
            )
            db.add_all([alice, bob])
            db.flush()

            alice_sphere = Sphere(owner_id=alice.id, name="Alice work")
            bob_sphere = Sphere(owner_id=bob.id, name="Bob work")
            db.add_all([alice_sphere, bob_sphere])
            db.flush()

            alice_project = Project(
                owner_id=alice.id, sphere_id=alice_sphere.id, name="Atlas"
            )
            bob_project = Project(
                owner_id=bob.id, sphere_id=bob_sphere.id, name="Bob project"
            )
            alice_person = Person(owner_id=alice.id, name="Ann")
            bob_person = Person(owner_id=bob.id, name="Bob person")
            db.add_all([alice_project, bob_project, alice_person, bob_person])
            db.commit()

            self.alice_sphere = alice_sphere.id
            self.bob_sphere = bob_sphere.id
            self.alice_project = alice_project.id
            self.bob_project = bob_project.id
            self.alice_person = alice_person.id
            self.bob_person = bob_person.id

        self.alice = TestClient(self.app)
        self.bob = TestClient(self.app)
        self._login(self.alice, ALICE)
        self._login(self.bob, BOB)

    def tearDown(self) -> None:
        self.alice.close()
        self.bob.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post("/api/auth/login", json=user)
        self.assertEqual(response.status_code, 200, response.text)

    def _create(self, client: TestClient, **payload) -> dict:
        response = client.post("/api/tasks", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _set_updated_at(self, task_id: int, value) -> None:
        with self.app.state.SessionLocal() as db:
            db.get(Task, task_id).updated_at = value
            db.commit()

    # 1. CRUD + 401
    def test_crud_and_auth(self) -> None:
        task = self._create(
            self.alice, title="Write report", priority="high", tags=["work"]
        )
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["tags"], ["work"])
        task_id = task["id"]

        card = self.alice.get(f"/api/tasks/{task_id}")
        self.assertEqual(card.status_code, 200, card.text)
        self.assertEqual(card.json()["title"], "Write report")
        self.assertEqual(card.json()["subtasks"], [])
        self.assertEqual(card.json()["blocked_by"], [])
        self.assertEqual(card.json()["people"], [])

        patched = self.alice.patch(
            f"/api/tasks/{task_id}", json={"description": "draft", "status": "doing"}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["description"], "draft")
        self.assertEqual(patched.json()["status"], "doing")

        listed = self.alice.get("/api/tasks")
        self.assertEqual([t["id"] for t in listed.json()], [task_id])

        self.assertEqual(self.alice.get(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(self.alice.delete(f"/api/tasks/{task_id}").status_code, 204)
        self.assertEqual(self.alice.get(f"/api/tasks/{task_id}").status_code, 404)
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{task_id}", json={"title": "gone"}
            ).status_code,
            404,
        )

        with TestClient(self.app) as anon:
            self.assertEqual(anon.get("/api/tasks").status_code, 401)
            self.assertEqual(anon.post("/api/tasks", json={"title": "x"}).status_code, 401)

    # 2. Подзадачи
    def test_subtasks(self) -> None:
        parent = self._create(self.alice, title="Parent")
        child = self._create(
            self.alice, title="Child", parent_id=parent["id"]
        )
        card = self.alice.get(f"/api/tasks/{parent['id']}").json()
        self.assertEqual([s["id"] for s in card["subtasks"]], [child["id"]])
        self.assertEqual(card["subtasks"][0]["parent_id"], parent["id"])

        # Каскад: удаление родителя убирает подзадачу.
        self.assertEqual(self.alice.delete(f"/api/tasks/{parent['id']}").status_code, 204)
        self.assertEqual(self.alice.get(f"/api/tasks/{child['id']}").status_code, 404)

    # 3. Зависимости и блокировка doing
    def test_dependencies_block_doing(self) -> None:
        blocker = self._create(self.alice, title="Blocker")
        task = self._create(
            self.alice, title="Blocked", blocked_by=[blocker["id"]]
        )
        card = self.alice.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(
            card["blocked_by"],
            [{"id": blocker["id"], "title": "Blocker", "status": "todo"}],
        )

        blocked = self.alice.patch(
            f"/api/tasks/{task['id']}", json={"status": "doing"}
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["blockers"][0]["id"], blocker["id"])
        created_doing = self.alice.post(
            "/api/tasks",
            json={
                "title": "Doing now",
                "status": "doing",
                "blocked_by": [blocker["id"]],
            },
        )
        self.assertEqual(created_doing.status_code, 409, created_doing.text)

        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{blocker['id']}", json={"status": "done"}
            ).status_code,
            200,
        )
        doing = self.alice.patch(
            f"/api/tasks/{task['id']}", json={"status": "doing"}
        )
        self.assertEqual(doing.status_code, 200, doing.text)
        self.assertEqual(doing.json()["status"], "doing")

        # PATCH blocked_by — полная замена набора.
        replaced = self.alice.patch(
            f"/api/tasks/{task['id']}", json={"blocked_by": []}
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertEqual(
            self.alice.get(f"/api/tasks/{task['id']}").json()["blocked_by"], []
        )

        # self, прямой цикл и null-набор → 422.
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{task['id']}", json={"blocked_by": [task["id"]]}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{task['id']}", json={"blocked_by": None}
            ).status_code,
            422,
        )
        a = self._create(self.alice, title="A")
        b = self._create(self.alice, title="B", blocked_by=[a["id"]])
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{a['id']}", json={"blocked_by": [b["id"]]}
            ).status_code,
            422,
        )

        # Чужой блокер → 404, каскад удаления зависимости.
        bob_task = self._create(self.bob, title="Bob task")
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{task['id']}", json={"blocked_by": [bob_task["id"]]}
            ).status_code,
            404,
        )
        self.assertEqual(self.alice.delete(f"/api/tasks/{blocker['id']}").status_code, 204)
        # blocker уже отвязан; связывает заново и удаляет блокер.
        self.alice.patch(f"/api/tasks/{task['id']}", json={"blocked_by": [b["id"]]})
        self.alice.delete(f"/api/tasks/{b['id']}")
        self.assertEqual(
            self.alice.get(f"/api/tasks/{task['id']}").json()["blocked_by"], []
        )

    # 4. RRULE
    def test_rrule_creates_next_occurrence(self) -> None:
        task = self._create(
            self.alice,
            title="Daily",
            rrule=" RRULE:FREQ=DAILY;INTERVAL=1 ",
            due_at="2026-12-01T09:00:00",
        )
        # Префикс `RRULE:` срезан (иначе в ICS получается RRULE:RRULE:...).
        self.assertEqual(task["rrule"], "FREQ=DAILY;INTERVAL=1")
        with self.app.state.SessionLocal() as db:
            self.assertEqual(
                db.get(Task, task["id"]).rrule, "FREQ=DAILY;INTERVAL=1"
            )

        done = self.alice.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(body["status"], "done")
        nxt = body["next_task"]
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["status"], "todo")
        self.assertEqual(nxt["title"], "Daily")
        self.assertEqual(nxt["due_at"], "2026-12-02T09:00:00")
        self.assertEqual(nxt["rrule"], "FREQ=DAILY;INTERVAL=1")

        # Повторное done не создаёт ещё один экземпляр.
        again = self.alice.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        self.assertIsNone(again.json()["next_task"])

        # Следующий экземпляр тоже повторяется.
        third = self.alice.patch(
            f"/api/tasks/{nxt['id']}", json={"status": "done"}
        ).json()["next_task"]
        self.assertEqual(third["due_at"], "2026-12-03T09:00:00")

        # PATCH тоже нормализует (префикс в любом регистре).
        weekly = self._create(self.alice, title="Weekly")
        patched = self.alice.patch(
            f"/api/tasks/{weekly['id']}", json={"rrule": "rrule:FREQ=WEEKLY"}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["rrule"], "FREQ=WEEKLY")
        with self.app.state.SessionLocal() as db:
            self.assertEqual(db.get(Task, weekly["id"]).rrule, "FREQ=WEEKLY")

        # Невалидное, пустое и многострочное (инъекция) → 422.
        for bad in (
            "FREQ=NOPE",
            "RRULE:",
            "   ",
            "FREQ=DAILY\nRRULE:FREQ=WEEKLY",
            "FREQ=DAILY\r\n",
        ):
            response = self.alice.post(
                "/api/tasks", json={"title": "Bad", "rrule": bad}
            )
            self.assertEqual(response.status_code, 422, bad)
        self.assertEqual(
            self.alice.patch(
                f"/api/tasks/{weekly['id']}",
                json={"rrule": "FREQ=DAILY\nX-INJECT: 1"},
            ).status_code,
            422,
        )
        with self.app.state.SessionLocal() as db:
            self.assertEqual(db.get(Task, weekly["id"]).rrule, "FREQ=WEEKLY")

    # 5. Фильтры
    def test_filters(self) -> None:
        now = utcnow()
        overdue = self._create(
            self.alice,
            title="Overdue",
            due_at=(now - timedelta(days=2)).isoformat(),
        )
        closed = self._create(
            self.alice,
            title="Closed overdue",
            due_at=(now - timedelta(days=2)).isoformat(),
        )
        self.alice.patch(f"/api/tasks/{closed['id']}", json={"status": "cancelled"})
        tagged = self._create(
            self.alice,
            title="Tagged",
            priority="high",
            tags=["home"],
            project_id=self.alice_project,
            sphere_id=self.alice_sphere,
        )
        stale = self._create(self.alice, title="Stale")
        self._set_updated_at(stale["id"], now - timedelta(days=10))

        def ids(response) -> list[int]:
            return [t["id"] for t in response.json()]

        self.assertEqual(ids(self.alice.get("/api/tasks?overdue=true")), [overdue["id"]])
        self.assertEqual(
            ids(self.alice.get("/api/tasks?stale_days=5")), [stale["id"]]
        )
        self.assertEqual(
            ids(self.alice.get(f"/api/tasks?project_id={self.alice_project}")),
            [tagged["id"]],
        )
        self.assertEqual(
            ids(self.alice.get(f"/api/tasks?sphere_id={self.alice_sphere}")),
            [tagged["id"]],
        )
        self.assertEqual(
            ids(self.alice.get("/api/tasks?tag=home")), [tagged["id"]]
        )
        self.assertEqual(
            ids(self.alice.get("/api/tasks?status=cancelled")), [closed["id"]]
        )
        self.assertEqual(
            ids(self.alice.get("/api/tasks?priority=high")), [tagged["id"]]
        )
        self.assertEqual(
            ids(
                self.alice.get(
                    f"/api/tasks?due_before={(now + timedelta(days=1)).isoformat()}"
                )
            ),
            [overdue["id"], closed["id"]],
        )

        # Чужие sphere/project в фильтре → 404.
        self.assertEqual(
            self.alice.get(f"/api/tasks?project_id={self.bob_project}").status_code,
            404,
        )
        self.assertEqual(
            self.alice.get(f"/api/tasks?sphere_id={self.bob_sphere}").status_code,
            404,
        )

    def test_sort(self) -> None:
        self._create(self.alice, title="No due", priority="high")
        self._create(
            self.alice, title="Later", priority="low", due_at="2030-01-01T00:00:00"
        )
        self._create(
            self.alice, title="Sooner", priority="medium", due_at="2029-01-01T00:00:00"
        )

        def titles(path: str) -> list[str]:
            return [t["title"] for t in self.alice.get(path).json()]

        self.assertEqual(titles("/api/tasks"), ["Sooner", "Later", "No due"])
        self.assertEqual(
            titles("/api/tasks?sort=due_at"), ["Sooner", "Later", "No due"]
        )
        self.assertEqual(
            titles("/api/tasks?sort=priority"), ["No due", "Sooner", "Later"]
        )

        now = utcnow()
        was = {"Sooner": 1, "No due": 3, "Later": 5}
        with self.app.state.SessionLocal() as db:
            for title, days in was.items():
                db.query(Task).filter_by(title=title).one().updated_at = (
                    now - timedelta(days=days)
                )
            db.commit()
        self.assertEqual(
            titles("/api/tasks?sort=updated_at"), ["Sooner", "No due", "Later"]
        )

    # 6. Связи с людьми
    def test_task_people(self) -> None:
        task = self._create(self.alice, title="Meet")
        link = self.alice.post(
            f"/api/tasks/{task['id']}/people",
            json={"person_id": self.alice_person, "role": "owner"},
        )
        self.assertEqual(link.status_code, 200, link.text)
        self.assertEqual(
            link.json(),
            {"person_id": self.alice_person, "name": "Ann", "role": "owner"},
        )

        # Повторный POST обновляет роль, а не падает на PK.
        self.alice.post(
            f"/api/tasks/{task['id']}/people",
            json={"person_id": self.alice_person, "role": "assistant"},
        )
        people = self.alice.get(f"/api/tasks/{task['id']}/people").json()
        self.assertEqual(
            people,
            [{"person_id": self.alice_person, "name": "Ann", "role": "assistant"}],
        )
        self.assertEqual(
            self.alice.get(f"/api/tasks/{task['id']}").json()["people"], people
        )

        self.assertEqual(
            self.alice.post(
                f"/api/tasks/{task['id']}/people",
                json={"person_id": self.bob_person},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.alice.delete(
                f"/api/tasks/{task['id']}/people/{self.alice_person}"
            ).status_code,
            204,
        )
        self.assertEqual(
            self.alice.get(f"/api/tasks/{task['id']}/people").json(), []
        )

    # 7. Изоляция
    def test_isolation(self) -> None:
        task = self._create(self.alice, title="Secret")
        self.assertEqual(self.bob.get("/api/tasks").json(), [])
        self.assertEqual(self.bob.get(f"/api/tasks/{task['id']}").status_code, 404)
        self.assertEqual(
            self.bob.patch(
                f"/api/tasks/{task['id']}", json={"title": "stolen"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.bob.delete(f"/api/tasks/{task['id']}").status_code, 404
        )

        bob_task = self._create(self.bob, title="Bob task")
        for payload in (
            {"title": "x", "sphere_id": self.alice_sphere},
            {"title": "x", "project_id": self.alice_project},
            {"title": "x", "parent_id": task["id"]},
            {"title": "x", "blocked_by": [task["id"]]},
        ):
            self.assertEqual(
                self.bob.post("/api/tasks", json=payload).status_code, 404
            )
        self.assertEqual(
            self.bob.patch(
                f"/api/tasks/{bob_task['id']}", json={"parent_id": task["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.bob.post(
                f"/api/tasks/{task['id']}/people",
                json={"person_id": self.bob_person},
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
