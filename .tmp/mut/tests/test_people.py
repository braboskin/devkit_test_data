"""FR-17 / A17: люди — контакты, привязки, карточка, поиск, изоляция, каскад."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import (
    Event,
    EventParticipant,
    Person,
    PersonProject,
    PersonSphere,
    Project,
    Sphere,
    Task,
    TaskPerson,
    User,
)

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}


class PeopleTests(unittest.TestCase):
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
            db.commit()
            self.alice_id, self.bob_id = alice.id, bob.id

            sphere = Sphere(owner_id=alice.id, name="Работа")
            other = Sphere(owner_id=bob.id, name="Личное")
            db.add_all([sphere, other])
            db.commit()
            self.sphere_id, self.bob_sphere_id = sphere.id, other.id

            project = Project(owner_id=alice.id, sphere_id=sphere.id, name="Атлас")
            db.add(project)
            db.commit()
            self.project_id = project.id

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post("/api/auth/login", json=user)
        self.assertEqual(response.status_code, 200, response.text)

    def _create(self, client: TestClient, **overrides) -> dict:
        payload = {"name": "Тест", "contacts": {}, "tags": []}
        payload.update(overrides)
        response = client.post("/api/people", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_and_card(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = self._create(
                client,
                name="  Анна  ",
                contacts={
                    "phone": "+7 999 000-00-00",
                    "email": "anna@example.com",
                    "telegram": "@anna",
                },
                birth_date="1990-05-17",
                relation="друг",
                notes="любит кофе",
                tags=["семья", "кофе"],
            )
            self.assertEqual(created["name"], "Анна")
            self.assertEqual(created["birth_date"], "1990-05-17")
            self.assertEqual(created["tags"], ["семья", "кофе"])

            person_id = created["id"]
            card = client.get(f"/api/people/{person_id}")
            self.assertEqual(card.status_code, 200, card.text)
            body = card.json()
            self.assertEqual(body["name"], "Анна")
            self.assertEqual(body["contacts"]["phone"], "+7 999 000-00-00")
            self.assertEqual(body["notes"], "любит кофе")
            self.assertEqual(body["relation"], "друг")
            self.assertEqual(
                body["relations"],
                {"spheres": [], "projects": [], "events": [], "tasks": []},
            )

            # name обязателен, обрезается и ограничен 200 символами.
            blank = client.post("/api/people", json={"name": "   "})
            self.assertEqual(blank.status_code, 422, blank.text)
            too_long = client.post("/api/people", json={"name": "x" * 201})
            self.assertEqual(too_long.status_code, 422, too_long.text)

    def test_links_and_relations(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            person_id = self._create(client, name="Анна")["id"]

            sphere_link = client.post(
                f"/api/people/{person_id}/spheres",
                json={"sphere_id": self.sphere_id, "role": "коллега"},
            )
            self.assertEqual(sphere_link.status_code, 201, sphere_link.text)
            project_link = client.post(
                f"/api/people/{person_id}/projects",
                json={"project_id": self.project_id, "role": "лид"},
            )
            self.assertEqual(project_link.status_code, 201, project_link.text)

            relations = client.get(f"/api/people/{person_id}/relations")
            self.assertEqual(relations.status_code, 200, relations.text)
            self.assertEqual(
                relations.json()["spheres"],
                [{"id": self.sphere_id, "name": "Работа", "role": "коллега"}],
            )
            self.assertEqual(
                relations.json()["projects"],
                [{"id": self.project_id, "name": "Атлас", "role": "лид"}],
            )

            card = client.get(f"/api/people/{person_id}").json()
            self.assertEqual(card["relations"], relations.json())

            removed = client.delete(
                f"/api/people/{person_id}/spheres/{self.sphere_id}"
            )
            self.assertEqual(removed.status_code, 204, removed.text)
            self.assertEqual(
                client.get(f"/api/people/{person_id}/relations").json()["spheres"],
                [],
            )
            self.assertEqual(
                client.get(f"/api/people/{person_id}/relations").json()["projects"],
                [{"id": self.project_id, "name": "Атлас", "role": "лид"}],
            )
            again = client.delete(
                f"/api/people/{person_id}/spheres/{self.sphere_id}"
            )
            self.assertEqual(again.status_code, 404, again.text)

    def test_card_shows_event_and_task_links(self) -> None:
        with self.app.state.SessionLocal() as db:
            event = Event(
                owner_id=self.alice_id,
                title="Созвон",
                start_at=datetime(2026, 1, 2, 10, 0),
            )
            task = Task(owner_id=self.alice_id, title="Отчёт", status="doing")
            db.add_all([event, task])
            db.commit()
            person = Person(owner_id=self.alice_id, name="Анна")
            db.add(person)
            db.commit()
            db.add_all(
                [
                    EventParticipant(
                        event_id=event.id,
                        person_id=person.id,
                        owner_id=self.alice_id,
                        role="гость",
                    ),
                    TaskPerson(
                        task_id=task.id,
                        person_id=person.id,
                        owner_id=self.alice_id,
                        role="исполнитель",
                    ),
                ]
            )
            db.commit()
            person_id, event_id, task_id = person.id, event.id, task.id

        with TestClient(self.app) as client:
            self._login(client, ALICE)
            relations = client.get(f"/api/people/{person_id}/relations")
            self.assertEqual(relations.status_code, 200, relations.text)
            body = relations.json()
            self.assertEqual(len(body["events"]), 1)
            self.assertEqual(body["events"][0]["id"], event_id)
            self.assertEqual(body["events"][0]["title"], "Созвон")
            self.assertEqual(body["events"][0]["role"], "гость")
            self.assertTrue(body["events"][0]["start_at"].startswith("2026-01-02T10:00:00"))
            self.assertEqual(
                body["tasks"],
                [
                    {
                        "id": task_id,
                        "title": "Отчёт",
                        "status": "doing",
                        "role": "исполнитель",
                    }
                ],
            )
            card = client.get(f"/api/people/{person_id}").json()
            self.assertEqual(card["relations"], body)

    def test_search_and_isolation(self) -> None:
        with TestClient(self.app) as alice_client, TestClient(self.app) as bob_client:
            self._login(alice_client, ALICE)
            self._login(bob_client, BOB)
            anna = self._create(
                alice_client, name="Анна Смирнова", tags=["семья"]
            )["id"]
            boris = self._create(
                alice_client, name="Борис", tags=["работа"]
            )["id"]
            bob_person = self._create(bob_client, name="Анна Бобова")["id"]

            response = alice_client.post(
                f"/api/people/{anna}/spheres",
                json={"sphere_id": self.sphere_id},
            )
            self.assertEqual(response.status_code, 201, response.text)
            alice_client.post(
                f"/api/people/{anna}/projects",
                json={"project_id": self.project_id},
            )

            def names(response) -> list[str]:
                self.assertEqual(response.status_code, 200, response.text)
                return sorted(person["name"] for person in response.json())

            self.assertEqual(
                names(alice_client.get("/api/people")),
                ["Анна Смирнова", "Борис"],
            )
            self.assertEqual(
                names(alice_client.get("/api/people", params={"q": "анна"})),
                ["Анна Смирнова"],
            )
            self.assertEqual(
                names(alice_client.get("/api/people", params={"q": "БОРИС"})),
                ["Борис"],
            )
            self.assertEqual(
                names(alice_client.get("/api/people", params={"tag": "семья"})),
                ["Анна Смирнова"],
            )
            self.assertEqual(
                names(
                    alice_client.get(
                        "/api/people", params={"sphere_id": self.sphere_id}
                    )
                ),
                ["Анна Смирнова"],
            )
            self.assertEqual(
                names(
                    alice_client.get(
                        "/api/people", params={"project_id": self.project_id}
                    )
                ),
                ["Анна Смирнова"],
            )

            # Чужая сфера в фильтре — 404, а не пустой список.
            foreign = alice_client.get(
                "/api/people", params={"sphere_id": self.bob_sphere_id}
            )
            self.assertEqual(foreign.status_code, 404, foreign.text)

            # B не видит людей A ни в списке, ни по id.
            self.assertEqual(
                names(bob_client.get("/api/people")), ["Анна Бобова"]
            )
            self.assertEqual(bob_client.get(f"/api/people/{anna}").status_code, 404)
            self.assertEqual(
                bob_client.get(f"/api/people/{anna}/relations").status_code, 404
            )
            self.assertNotEqual(anna, bob_person)

    def test_delete_cascades_links(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            person_id = self._create(client, name="Анна")["id"]
            client.post(
                f"/api/people/{person_id}/spheres",
                json={"sphere_id": self.sphere_id, "role": "коллега"},
            )
            client.post(
                f"/api/people/{person_id}/projects",
                json={"project_id": self.project_id, "role": "лид"},
            )

        with self.app.state.SessionLocal() as db:
            event = Event(
                owner_id=self.alice_id,
                title="Созвон",
                start_at=datetime(2026, 1, 2, 10, 0),
            )
            task = Task(owner_id=self.alice_id, title="Отчёт")
            db.add_all([event, task])
            db.commit()
            db.add_all(
                [
                    EventParticipant(
                        event_id=event.id,
                        person_id=person_id,
                        owner_id=self.alice_id,
                    ),
                    TaskPerson(
                        task_id=task.id,
                        person_id=person_id,
                        owner_id=self.alice_id,
                    ),
                ]
            )
            db.commit()

        with TestClient(self.app) as client:
            self._login(client, ALICE)
            response = client.delete(f"/api/people/{person_id}")
            self.assertEqual(response.status_code, 204, response.text)
            self.assertEqual(client.get(f"/api/people/{person_id}").status_code, 404)

        with self.app.state.SessionLocal() as db:
            self.assertIsNone(db.get(Person, person_id))
            self.assertEqual(
                db.query(PersonSphere).filter_by(person_id=person_id).count(), 0
            )
            self.assertEqual(
                db.query(PersonProject).filter_by(person_id=person_id).count(), 0
            )
            self.assertEqual(
                db.query(EventParticipant).filter_by(person_id=person_id).count(), 0
            )
            self.assertEqual(
                db.query(TaskPerson).filter_by(person_id=person_id).count(), 0
            )
            self.assertEqual(db.query(Event).count(), 1)
            self.assertEqual(db.query(Task).count(), 1)

    def test_requires_session_and_hides_foreign(self) -> None:
        with TestClient(self.app) as alice_client, TestClient(self.app) as bob_client:
            self._login(alice_client, ALICE)
            self._login(bob_client, BOB)
            person_id = self._create(alice_client, name="Анна")["id"]
            alice_client.post(
                f"/api/people/{person_id}/spheres",
                json={"sphere_id": self.sphere_id, "role": "коллега"},
            )

            with TestClient(self.app) as anonymous:
                self.assertEqual(anonymous.get("/api/people").status_code, 401)
                self.assertEqual(
                    anonymous.post("/api/people", json={"name": "X"}).status_code,
                    401,
                )
                self.assertEqual(
                    anonymous.get(f"/api/people/{person_id}").status_code, 401
                )
                self.assertEqual(
                    anonymous.patch(
                        f"/api/people/{person_id}", json={"name": "X"}
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    anonymous.delete(f"/api/people/{person_id}").status_code, 401
                )
                self.assertEqual(
                    anonymous.get(
                        f"/api/people/{person_id}/relations"
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    anonymous.post(
                        f"/api/people/{person_id}/spheres",
                        json={"sphere_id": self.sphere_id},
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    anonymous.delete(
                        f"/api/people/{person_id}/spheres/{self.sphere_id}"
                    ).status_code,
                    401,
                )

            for method, path in (
                ("get", f"/api/people/{person_id}"),
                ("patch", f"/api/people/{person_id}"),
                ("delete", f"/api/people/{person_id}"),
                ("get", f"/api/people/{person_id}/relations"),
            ):
                kwargs = {"json": {"name": "Взлом"}} if method == "patch" else {}
                response = getattr(bob_client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 404, f"{method} {path}")

            foreign_link = bob_client.post(
                f"/api/people/{person_id}/spheres",
                json={"sphere_id": self.sphere_id},
            )
            self.assertEqual(foreign_link.status_code, 404, foreign_link.text)
            foreign_unlink = bob_client.delete(
                f"/api/people/{person_id}/spheres/{self.sphere_id}"
            )
            self.assertEqual(foreign_unlink.status_code, 404, foreign_unlink.text)

            # Своя сфера чужого пользователя в привязке — тоже 404.
            bob_person = self._create(bob_client, name="Боб")["id"]
            foreign_sphere = bob_client.post(
                f"/api/people/{bob_person}/spheres",
                json={"sphere_id": self.sphere_id},
            )
            self.assertEqual(foreign_sphere.status_code, 404, foreign_sphere.text)

            # PATCH своих полей владельцем работает.
            patched = alice_client.patch(
                f"/api/people/{person_id}",
                json={"notes": "новые заметки", "tags": ["друг"]},
            )
            self.assertEqual(patched.status_code, 200, patched.text)
            self.assertEqual(patched.json()["notes"], "новые заметки")
            self.assertEqual(patched.json()["tags"], ["друг"])
            self.assertEqual(patched.json()["name"], "Анна")


if __name__ == "__main__":
    unittest.main()
