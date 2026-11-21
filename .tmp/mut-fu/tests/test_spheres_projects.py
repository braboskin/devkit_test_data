"""FR-3: CRUD сфер и проектов, изоляция владельцев, 409 при удалении."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Event, Task, User

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}


class SpheresProjectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{(Path(self.tmp.name) / 'test.db').as_posix()}"
        self.app = create_app(self.url)
        self.engine = self.app.state.engine
        Base.metadata.create_all(self.engine)
        with self.app.state.SessionLocal() as db:
            db.add_all(
                [
                    User(
                        username=ALICE["username"],
                        password_hash=hash_password(ALICE["password"]),
                    ),
                    User(
                        username=BOB["username"],
                        password_hash=hash_password(BOB["password"]),
                    ),
                ]
            )
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _clients(self) -> tuple[TestClient, TestClient]:
        alice = TestClient(self.app)
        bob = TestClient(self.app)
        self.addCleanup(alice.close)
        self.addCleanup(bob.close)
        self._login(alice, ALICE)
        self._login(bob, BOB)
        return alice, bob

    def _user_id(self, client: TestClient) -> str:
        return client.get("/api/me").json()["id"]

    def _create_sphere(self, client: TestClient, name: str = "Work") -> dict:
        response = client.post("/api/spheres", json={"name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _create_project(
        self, client: TestClient, sphere_id: int, **overrides
    ) -> dict:
        payload = {"sphere_id": sphere_id, "name": "Site"}
        payload.update(overrides)
        response = client.post("/api/projects", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_sphere_crud(self) -> None:
        alice, _ = self._clients()

        created = self._create_sphere(alice, "  Work  ")
        self.assertEqual(created["name"], "Work")
        self.assertIsInstance(created["id"], int)
        self.assertIn("created_at", created)

        fetched = alice.get(f"/api/spheres/{created['id']}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json(), created)

        self._create_sphere(alice, "Zeta")
        self._create_sphere(alice, "Alpha")
        listed = alice.get("/api/spheres")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([s["name"] for s in listed.json()], ["Alpha", "Work", "Zeta"])

        updated = alice.patch(
            f"/api/spheres/{created['id']}", json={"name": "Job"}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Job")

        deleted = alice.delete(f"/api/spheres/{created['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(deleted.content, b"")
        names = [s["name"] for s in alice.get("/api/spheres").json()]
        self.assertNotIn("Job", names)

    def test_project_crud(self) -> None:
        alice, _ = self._clients()
        sphere = self._create_sphere(alice)
        other = self._create_sphere(alice, "Home")

        created = self._create_project(
            alice,
            sphere["id"],
            name="  Site  ",
            description="landing",
            status="planned",
            due_at="2026-03-01T09:30:00",
        )
        self.assertEqual(created["name"], "Site")
        self.assertEqual(created["description"], "landing")
        self.assertEqual(created["status"], "planned")
        self.assertEqual(created["sphere_id"], sphere["id"])
        self.assertEqual(created["due_at"], "2026-03-01T09:30:00")
        self.assertEqual(
            datetime.fromisoformat(created["due_at"]), datetime(2026, 3, 1, 9, 30)
        )

        default_status = self._create_project(alice, sphere["id"], name="Inbox")
        self.assertEqual(default_status["status"], "active")

        listed = alice.get("/api/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 2)
        self.assertEqual(
            alice.get(f"/api/projects/{created['id']}").json(), created
        )

        by_sphere = alice.get("/api/projects", params={"sphere_id": sphere["id"]})
        self.assertEqual(by_sphere.status_code, 200, by_sphere.text)
        self.assertEqual(
            {p["id"] for p in by_sphere.json()},
            {created["id"], default_status["id"]},
        )
        empty = alice.get("/api/projects", params={"sphere_id": other["id"]})
        self.assertEqual(empty.json(), [])

        updated = alice.patch(
            f"/api/projects/{created['id']}",
            json={
                "name": "Site v2",
                "status": "done",
                "description": None,
                "due_at": None,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["name"], "Site v2")
        self.assertEqual(body["status"], "done")
        self.assertIsNone(body["description"])
        self.assertIsNone(body["due_at"])

        moved = alice.patch(
            f"/api/projects/{default_status['id']}",
            json={"due_at": "2026-03-01T09:30:00+03:00"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["due_at"], "2026-03-01T06:30:00")

        deleted = alice.delete(f"/api/projects/{created['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertNotIn(
            created["id"], [p["id"] for p in alice.get("/api/projects").json()]
        )

    def test_foreign_ids_are_404_and_lists_isolated(self) -> None:
        alice, bob = self._clients()
        sphere = self._create_sphere(alice, "Secret")
        project = self._create_project(alice, sphere["id"], name="Secret site")

        # В списках чужих сфер/проектов нет (GET изоляция).
        self.assertEqual(bob.get("/api/spheres").json(), [])
        self.assertEqual(bob.get("/api/projects").json(), [])
        self.assertEqual(bob.get(f"/api/spheres/{sphere['id']}").status_code, 404)
        self.assertEqual(bob.get(f"/api/projects/{project['id']}").status_code, 404)

        self.assertEqual(
            bob.patch(
                f"/api/spheres/{sphere['id']}", json={"name": "Hijack"}
            ).status_code,
            404,
        )
        self.assertEqual(bob.delete(f"/api/spheres/{sphere['id']}").status_code, 404)

        self.assertEqual(
            bob.get("/api/projects", params={"sphere_id": sphere["id"]}).status_code,
            404,
        )
        self.assertEqual(
            bob.patch(
                f"/api/projects/{project['id']}", json={"name": "Hijack"}
            ).status_code,
            404,
        )
        self.assertEqual(
            bob.delete(f"/api/projects/{project['id']}").status_code, 404
        )

        # Чужие id не изменились и не удалились.
        self.assertEqual(
            alice.get("/api/spheres").json()[0]["name"], "Secret"
        )
        self.assertEqual(
            alice.get("/api/projects").json()[0]["name"], "Secret site"
        )

    def test_requires_session(self) -> None:
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/spheres").status_code, 401)
            self.assertEqual(
                client.post("/api/spheres", json={"name": "X"}).status_code, 401
            )
            self.assertEqual(client.get("/api/projects").status_code, 401)
            self.assertEqual(
                client.post(
                    "/api/projects", json={"sphere_id": 1, "name": "X"}
                ).status_code,
                401,
            )

    def test_delete_sphere_with_projects_is_409(self) -> None:
        alice, _ = self._clients()
        sphere = self._create_sphere(alice)
        project = self._create_project(alice, sphere["id"])

        response = alice.delete(f"/api/spheres/{sphere['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["projects"], 1)
        self.assertEqual(response.json()["tasks"], 0)
        self.assertEqual(response.json()["events"], 0)
        self.assertIn("detail", response.json())

        # Ничего не удалено.
        self.assertEqual(
            [s["id"] for s in alice.get("/api/spheres").json()], [sphere["id"]]
        )
        self.assertEqual(
            [p["id"] for p in alice.get("/api/projects").json()], [project["id"]]
        )

        self.assertEqual(
            alice.delete(f"/api/projects/{project['id']}").status_code, 204
        )
        self.assertEqual(
            alice.delete(f"/api/spheres/{sphere['id']}").status_code, 204
        )

    def test_delete_sphere_with_linked_task_or_event_is_409(self) -> None:
        alice, _ = self._clients()
        sphere = self._create_sphere(alice)
        alice_id = self._user_id(alice)
        with self.app.state.SessionLocal() as db:
            db.add(Task(owner_id=alice_id, sphere_id=sphere["id"], title="Task"))
            db.add(
                Event(
                    owner_id=alice_id,
                    sphere_id=sphere["id"],
                    title="Event",
                    start_at=datetime(2026, 1, 1, 10, 0),
                )
            )
            db.commit()

        response = alice.delete(f"/api/spheres/{sphere['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        body = response.json()
        self.assertEqual(
            (body["projects"], body["tasks"], body["events"]), (0, 1, 1)
        )
        self.assertEqual(
            [s["id"] for s in alice.get("/api/spheres").json()], [sphere["id"]]
        )

        with self.app.state.SessionLocal() as db:
            db.query(Task).delete()
            db.query(Event).delete()
            db.commit()
        self.assertEqual(
            alice.delete(f"/api/spheres/{sphere['id']}").status_code, 204
        )

    def test_delete_project_with_links_is_409(self) -> None:
        alice, _ = self._clients()
        sphere = self._create_sphere(alice)
        project = self._create_project(alice, sphere["id"])
        alice_id = self._user_id(alice)
        with self.app.state.SessionLocal() as db:
            db.add(Task(owner_id=alice_id, project_id=project["id"], title="Task"))
            db.add(
                Event(
                    owner_id=alice_id,
                    project_id=project["id"],
                    title="Event",
                    start_at=datetime(2026, 1, 1, 10, 0),
                )
            )
            db.commit()

        response = alice.delete(f"/api/projects/{project['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["tasks"], 1)
        self.assertEqual(response.json()["events"], 1)
        self.assertEqual(
            [p["id"] for p in alice.get("/api/projects").json()], [project["id"]]
        )

        with self.app.state.SessionLocal() as db:
            db.query(Task).delete()
            db.query(Event).delete()
            db.commit()
        self.assertEqual(
            alice.delete(f"/api/projects/{project['id']}").status_code, 204
        )

    def test_move_project_between_own_spheres(self) -> None:
        alice, bob = self._clients()
        first = self._create_sphere(alice, "First")
        second = self._create_sphere(alice, "Second")
        project = self._create_project(alice, first["id"])

        moved = alice.patch(
            f"/api/projects/{project['id']}", json={"sphere_id": second["id"]}
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["sphere_id"], second["id"])
        self.assertEqual(
            alice.get("/api/projects", params={"sphere_id": first["id"]}).json(), []
        )
        self.assertEqual(
            [
                p["id"]
                for p in alice.get(
                    "/api/projects", params={"sphere_id": second["id"]}
                ).json()
            ],
            [project["id"]],
        )

        bob_sphere = self._create_sphere(bob, "Bob")
        refused = alice.patch(
            f"/api/projects/{project['id']}", json={"sphere_id": bob_sphere["id"]}
        )
        self.assertEqual(refused.status_code, 404, refused.text)
        self.assertEqual(
            alice.get("/api/projects").json()[0]["sphere_id"], second["id"]
        )

    def test_validation(self) -> None:
        alice, bob = self._clients()
        sphere = self._create_sphere(alice)
        bob_sphere = self._create_sphere(bob, "Bob")

        blank = [
            alice.post("/api/spheres", json={"name": "   "}),
            alice.post("/api/spheres", json={"name": ""}),
            alice.post("/api/spheres", json={"name": "x" * 121}),
            alice.post(
                "/api/projects", json={"sphere_id": sphere["id"], "name": "  "}
            ),
            alice.post(
                "/api/projects",
                json={"sphere_id": sphere["id"], "name": "X", "status": "bogus"},
            ),
            alice.patch(f"/api/spheres/{sphere['id']}", json={"name": " "}),
        ]
        for response in blank:
            self.assertEqual(response.status_code, 422, response.text)

        # Проект можно создать только в своей сфере.
        self.assertEqual(
            alice.post(
                "/api/projects", json={"sphere_id": bob_sphere["id"], "name": "X"}
            ).status_code,
            404,
        )
        # Поля, которые не могут быть null, не принимают null в PATCH.
        project = self._create_project(alice, sphere["id"])
        for payload in (
            {"name": None},
            {"status": None},
            {"sphere_id": None},
        ):
            response = alice.patch(f"/api/projects/{project['id']}", json=payload)
            self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
