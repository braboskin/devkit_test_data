"""A1/A5/A6/A17: независимая проверка изоляции пользователей и приёмки M1.

Матрица маршрутов строится из OpenAPI приложения (фактические роутеры), а не
из списка в тесте: новый `/api/*`-маршрут автоматически проверяется на 401 и
на 404 по чужому id.
"""
import re
import tempfile
import unittest
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
    Task,
    TaskPerson,
    User,
)

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}

# Маршруты, которым сессия не нужна: вход/выход и публичный .ics по токену.
PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/calendars/{scope}.ics"),
}

# Маршрут владеет объектом, если в шаблоне есть id доменной сущности.
OWNED_ID = re.compile(
    r"\{(sphere_id|project_id|person_id|task_id|event_id)\}"
)


class IsolationTests(unittest.TestCase):
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

        self.alice = TestClient(self.app)
        self.bob = TestClient(self.app)
        self._login(self.alice, ALICE)
        self._login(self.bob, BOB)

    def tearDown(self) -> None:
        self.alice.close()
        self.bob.close()
        self.engine.dispose()
        self.tmp.cleanup()

    # ---------- helpers ----------

    def _login(self, client: TestClient, user: dict) -> None:
        response = client.post("/api/auth/login", json=user)
        self.assertEqual(response.status_code, 200, response.text)

    def _ok(self, response, code: int = 200) -> dict:
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def _create_sphere(self, client: TestClient, name: str = "Работа") -> dict:
        return self._ok(client.post("/api/spheres", json={"name": name}), 201)

    def _create_project(
        self, client: TestClient, sphere_id: int, name: str = "Атлас"
    ) -> dict:
        return self._ok(
            client.post(
                "/api/projects", json={"sphere_id": sphere_id, "name": name}
            ),
            201,
        )

    def _create_person(self, client: TestClient, name: str = "Анна", **extra) -> dict:
        payload = {"name": name}
        payload.update(extra)
        return self._ok(client.post("/api/people", json=payload), 201)

    def _create_task(self, client: TestClient, **payload) -> dict:
        return self._ok(client.post("/api/tasks", json=payload), 201)

    def _create_event(self, client: TestClient, **payload) -> dict:
        body = {
            "title": "Созвон",
            "start_at": "2026-03-01T10:00:00",
            "end_at": "2026-03-01T11:00:00",
        }
        body.update(payload)
        return self._ok(client.post("/api/events", json=body), 201)

    def _alice_graph(self) -> dict:
        """Полный граф объектов alice через API (он же владелец)."""
        sphere = self._create_sphere(self.alice)
        project = self._create_project(self.alice, sphere["id"])
        person = self._create_person(self.alice)
        task = self._create_task(self.alice, title="Задача")
        event = self._create_event(self.alice)
        return {
            "sphere_id": sphere["id"],
            "project_id": project["id"],
            "person_id": person["id"],
            "task_id": task["id"],
            "event_id": event["id"],
        }

    def _api_routes(self) -> list[tuple[str, str]]:
        spec = self.app.openapi()
        return sorted(
            (method.upper(), path)
            for path, operations in spec["paths"].items()
            if path.startswith("/api/")
            for method in operations
        )

    @staticmethod
    def _concrete_path(template: str, ids: dict) -> str:
        path = template
        for name, value in {**ids, "scope": "all"}.items():
            path = path.replace("{" + name + "}", str(value))
        return path

    def _body(self, method: str, template: str, ids: dict) -> dict | None:
        """Валидное тело запроса: иначе 422 маскирует 401/404."""
        if method in ("GET", "HEAD", "DELETE"):
            return None
        builders = {
            ("POST", "/api/spheres"): {"name": "Новая"},
            ("POST", "/api/projects"): {
                "sphere_id": ids["sphere_id"],
                "name": "Новый",
            },
            ("POST", "/api/people"): {"name": "Новый"},
            ("POST", "/api/people/{person_id}/spheres"): {
                "sphere_id": ids["sphere_id"]
            },
            ("POST", "/api/people/{person_id}/projects"): {
                "project_id": ids["project_id"]
            },
            ("POST", "/api/tasks"): {"title": "Новая"},
            ("POST", "/api/tasks/{task_id}/people"): {
                "person_id": ids["person_id"]
            },
            ("POST", "/api/events"): {
                "title": "Новое",
                "start_at": "2026-03-01T10:00:00",
            },
            ("POST", "/api/events/{event_id}/participants"): {
                "person_id": ids["person_id"]
            },
            ("POST", "/api/calendars/{scope}/token"): {},
            # M2: документы, задания, воркер и настройки. Тело — только чтобы
            # 422 не маскировал 401; id в шаблоне подставляется из целей e2e.
            ("POST", "/api/documents"): {},
            ("POST", "/api/documents/{document_id}/reprocess"): {},
            ("POST", "/api/documents/{document_id}/reindex"): {},
            ("POST", "/api/jobs/{job_id}/cancel"): {},
            ("POST", "/api/worker/claim"): {},
            ("POST", "/api/worker/jobs/{job_id}/heartbeat"): {},
            ("POST", "/api/worker/jobs/{job_id}/complete"): {"text": "текст"},
            ("POST", "/api/worker/jobs/{job_id}/fail"): {"error": "сбой"},
            ("POST", "/api/settings/worker-token"): {},
            ("PUT", "/api/settings/yadisk"): {"token": "test-token"},
            ("PATCH", "/api/spheres/{sphere_id}"): {"name": "Новая"},
            ("PATCH", "/api/projects/{project_id}"): {"name": "Новый"},
            ("PATCH", "/api/people/{person_id}"): {"name": "Новый"},
            ("PATCH", "/api/tasks/{task_id}"): {"title": "Новая"},
            ("PATCH", "/api/events/{event_id}"): {"title": "Новое"},
        }
        self.assertIn(
            (method, template),
            builders,
            f"добавь валидное тело запроса для {method} {template}",
        )
        return builders[(method, template)]

    # ---------- A1: матрица маршрутов ----------

    def test_anonymous_401_on_every_api_route(self) -> None:
        ids = self._alice_graph()
        routes = self._api_routes()
        self.assertTrue(routes, "маршруты API не найдены")
        with TestClient(self.app) as anon:
            for method, template in routes:
                if (method, template) in PUBLIC_ROUTES:
                    continue
                path = self._concrete_path(template, ids)
                body = self._body(method, template, ids)
                with self.subTest(method=method, path=template):
                    response = anon.request(method, path, json=body)
                    self.assertEqual(response.status_code, 401, response.text)

    def test_foreign_id_404_on_every_owned_route(self) -> None:
        ids = self._alice_graph()
        owned = [
            (method, template)
            for method, template in self._api_routes()
            if OWNED_ID.search(template)
        ]
        self.assertTrue(owned, "маршруты с id не найдены")
        for method, template in owned:
            path = self._concrete_path(template, ids)
            body = self._body(method, template, ids)
            with self.subTest(method=method, path=template):
                response = self.bob.request(method, path, json=body)
                self.assertEqual(response.status_code, 404, response.text)

        # После всех отказов объекты alice целы.
        for resource, own_id in (
            ("/api/spheres", ids["sphere_id"]),
            ("/api/projects", ids["project_id"]),
            ("/api/people", ids["person_id"]),
            ("/api/tasks", ids["task_id"]),
            ("/api/events", ids["event_id"]),
        ):
            with self.subTest(resource=resource):
                self.assertEqual(
                    self.alice.get(f"{resource}/{own_id}").status_code, 200
                )

    def test_foreign_objects_absent_from_lists(self) -> None:
        ids = self._alice_graph()
        bob_sphere = self._create_sphere(self.bob, "Личное")
        bob_person = self._create_person(self.bob, "Борис")
        bob_task = self._create_task(self.bob, title="Своя")
        bob_event = self._create_event(self.bob, title="Своё")

        self.assertEqual(
            [item["id"] for item in self._ok(self.bob.get("/api/spheres"))],
            [bob_sphere["id"]],
        )
        self.assertEqual(
            [item["id"] for item in self._ok(self.bob.get("/api/projects"))], []
        )
        self.assertEqual(
            [item["id"] for item in self._ok(self.bob.get("/api/people"))],
            [bob_person["id"]],
        )
        self.assertEqual(
            [item["id"] for item in self._ok(self.bob.get("/api/tasks"))],
            [bob_task["id"]],
        )
        self.assertEqual(
            [item["id"] for item in self._ok(self.bob.get("/api/events"))],
            [bob_event["id"]],
        )
        # Никаких следов чужих имён в выдаче.
        listed = self.bob.get("/api/people", params={"q": "Анна"})
        self.assertEqual(self._ok(listed), [])
        self.assertEqual(
            self._ok(self.bob.get("/api/people", params={"tag": "семья"})), []
        )
        for path in ("/api/spheres", "/api/projects", "/api/people",
                     "/api/tasks", "/api/events"):
            with self.subTest(path=path):
                text = self.alice.get(path).text
                self.assertNotIn(bob_person["name"], text)
                self.assertNotIn(bob_task["title"], text)
                self.assertNotIn("Своё", text)

    def test_foreign_filters_and_payload_ids_404(self) -> None:
        ids = self._alice_graph()
        bob_sphere = self._create_sphere(self.bob, "Боб")
        bob_project = self._create_project(self.bob, bob_sphere["id"], "Боб-проект")
        bob_person = self._create_person(self.bob, "Боб")
        bob_task = self._create_task(self.bob, title="Боб-задача")
        bob_event = self._create_event(self.bob, title="Боб-событие")

        # Фильтры списков по чужому id — 404, а не пустой список.
        for path, params in (
            ("/api/people", {"sphere_id": ids["sphere_id"]}),
            ("/api/people", {"project_id": ids["project_id"]}),
            ("/api/projects", {"sphere_id": ids["sphere_id"]}),
            ("/api/tasks", {"project_id": ids["project_id"]}),
            ("/api/tasks", {"sphere_id": ids["sphere_id"]}),
            ("/api/events", {"sphere_id": ids["sphere_id"]}),
            ("/api/events", {"project_id": ids["project_id"]}),
        ):
            with self.subTest(path=path, params=params):
                response = self.bob.get(path, params=params)
                self.assertEqual(response.status_code, 404, response.text)

        # Ссылки на чужое через тело запроса — 404.
        cases = [
            ("post", "/api/projects", {"sphere_id": ids["sphere_id"],
                                       "name": "Чужое"}),
            ("patch", f"/api/projects/{bob_project['id']}",
             {"sphere_id": ids["sphere_id"]}),
            ("post", f"/api/people/{bob_person['id']}/spheres",
             {"sphere_id": ids["sphere_id"]}),
            ("post", f"/api/people/{bob_person['id']}/projects",
             {"project_id": ids["project_id"]}),
            ("post", "/api/tasks", {"title": "x", "sphere_id": ids["sphere_id"]}),
            ("post", "/api/tasks",
             {"title": "x", "project_id": ids["project_id"]}),
            ("post", "/api/tasks", {"title": "x", "parent_id": ids["task_id"]}),
            ("post", "/api/tasks",
             {"title": "x", "blocked_by": [ids["task_id"]]}),
            ("patch", f"/api/tasks/{bob_task['id']}",
             {"parent_id": ids["task_id"]}),
            ("patch", f"/api/tasks/{bob_task['id']}",
             {"project_id": ids["project_id"]}),
            ("patch", f"/api/tasks/{bob_task['id']}",
             {"blocked_by": [ids["task_id"]]}),
            ("post", f"/api/tasks/{bob_task['id']}/people",
             {"person_id": ids["person_id"]}),
            ("post", "/api/events",
             {"title": "x", "start_at": "2026-03-01T10:00:00",
              "sphere_id": ids["sphere_id"]}),
            ("post", "/api/events",
             {"title": "x", "start_at": "2026-03-01T10:00:00",
              "project_id": ids["project_id"]}),
            ("patch", f"/api/events/{bob_event['id']}",
             {"sphere_id": ids["sphere_id"]}),
            ("patch", f"/api/events/{bob_event['id']}",
             {"project_id": ids["project_id"]}),
            ("post", f"/api/events/{bob_event['id']}/participants",
             {"person_id": ids["person_id"]}),
            ("post", f"/api/calendars/sphere-{ids['sphere_id']}/token", None),
            ("post", f"/api/calendars/project-{ids['project_id']}/token", None),
        ]
        for method, path, body in cases:
            with self.subTest(method=method, path=path, body=body):
                response = getattr(self.bob, method)(path, json=body)
                self.assertEqual(response.status_code, 404, response.text)

        # Связи и участия alice не изменились.
        self.assertEqual(
            self._ok(self.alice.get(f"/api/people/{ids['person_id']}/relations")),
            {"spheres": [], "projects": [], "events": [], "tasks": []},
        )
        self.assertEqual(
            self._ok(self.alice.get(f"/api/tasks/{ids['task_id']}/people")), []
        )
        self.assertEqual(
            self._ok(
                self.alice.get(f"/api/events/{ids['event_id']}/participants")
            ),
            [],
        )

    def test_calendar_token_isolated_between_users(self) -> None:
        alice_event = self._create_event(self.alice, title="Секрет alice")
        bob_event = self._create_event(self.bob, title="Событие боба")

        alice_token = self._ok(self.alice.post("/api/calendars/all/token"), 201)
        bob_token = self._ok(self.bob.post("/api/calendars/all/token"), 201)
        self.assertNotEqual(alice_token["token"], bob_token["token"])

        with TestClient(self.app) as anon:
            alice_feed = anon.get(alice_token["url"])
            self.assertEqual(alice_feed.status_code, 200, alice_feed.text)
            self.assertIn("text/calendar", alice_feed.headers["content-type"])
            self.assertIn(f"UID:{alice_event['id']}@atlas", alice_feed.text)
            self.assertNotIn(f"UID:{bob_event['id']}@atlas", alice_feed.text)

            bob_feed = anon.get(bob_token["url"])
            self.assertEqual(bob_feed.status_code, 200, bob_feed.text)
            self.assertIn(f"UID:{bob_event['id']}@atlas", bob_feed.text)
            self.assertNotIn(f"UID:{alice_event['id']}@atlas", bob_feed.text)

            # Чужой scope с токеном alice — 404, к данным bob не ведёт.
            bob_sphere = self._create_sphere(self.bob, "Боб")
            wrong_scope = anon.get(
                f"/api/calendars/sphere-{bob_sphere['id']}.ics"
                f"?token={alice_token['token']}"
            )
            self.assertEqual(wrong_scope.status_code, 404, wrong_scope.text)

            # Свой scope — свой токен и только свои данные.
            bob_scoped = self._ok(
                self.bob.post(
                    f"/api/calendars/sphere-{bob_sphere['id']}/token"
                ),
                201,
            )
            scoped_feed = anon.get(bob_scoped["url"])
            self.assertEqual(scoped_feed.status_code, 200, scoped_feed.text)
            self.assertNotIn(f"UID:{alice_event['id']}@atlas", scoped_feed.text)

    # ---------- A17: люди ----------

    def test_a17_people_full_acceptance(self) -> None:
        sphere = self._create_sphere(self.alice, "Работа")
        project = self._create_project(self.alice, sphere["id"], "Атлас")
        person = self._create_person(
            self.alice,
            name="  Анна Смирнова  ",
            contacts={
                "phone": "+7 999 000-00-00",
                "email": "anna@example.com",
                "telegram": "@anna",
            },
            birth_date="1990-05-17",
            relation="друг",
            notes="любит кофе",
            tags=["семья"],
        )
        person_id = person["id"]
        self.assertEqual(person["name"], "Анна Смирнова")
        self.assertEqual(person["birth_date"], "1990-05-17")

        # Привязки с ролью.
        self._ok(
            self.alice.post(
                f"/api/people/{person_id}/spheres",
                json={"sphere_id": sphere["id"], "role": "коллега"},
            ),
            201,
        )
        self._ok(
            self.alice.post(
                f"/api/people/{person_id}/projects",
                json={"project_id": project["id"], "role": "лид"},
            ),
            201,
        )

        # Участник события и человек в задаче с ролью.
        event = self._create_event(self.alice, title="Планирование")
        self._ok(
            self.alice.post(
                f"/api/events/{event['id']}/participants",
                json={"person_id": person_id, "role": "гость"},
            ),
            201,
        )
        task = self._create_task(self.alice, title="Отчёт", status="doing")
        self._ok(
            self.alice.post(
                f"/api/tasks/{task['id']}/people",
                json={"person_id": person_id, "role": "исполнитель"},
            )
        )

        # Карточка показывает контакты и все связи.
        card = self._ok(self.alice.get(f"/api/people/{person_id}"))
        self.assertEqual(card["contacts"]["phone"], "+7 999 000-00-00")
        self.assertEqual(card["contacts"]["email"], "anna@example.com")
        self.assertEqual(card["notes"], "любит кофе")
        relations = card["relations"]
        self.assertEqual(
            relations["spheres"],
            [{"id": sphere["id"], "name": "Работа", "role": "коллега"}],
        )
        self.assertEqual(
            relations["projects"],
            [{"id": project["id"], "name": "Атлас", "role": "лид"}],
        )
        self.assertEqual(
            [(e["id"], e["title"], e["role"]) for e in relations["events"]],
            [(event["id"], "Планирование", "гость")],
        )
        self.assertTrue(
            relations["events"][0]["start_at"].startswith("2026-03-01T10:00:00")
        )
        self.assertEqual(
            [
                (t["id"], t["title"], t["status"], t["role"])
                for t in relations["tasks"]
            ],
            [(task["id"], "Отчёт", "doing", "исполнитель")],
        )
        # Отдельный маршрут связей отдаёт то же.
        self.assertEqual(
            self._ok(self.alice.get(f"/api/people/{person_id}/relations")),
            relations,
        )

        # Поиск по имени (регистр не важен) и по тегу.
        self.assertEqual(
            [p["id"] for p in self._ok(
                self.alice.get("/api/people", params={"q": "анна"})
            )],
            [person_id],
        )
        self.assertEqual(
            [p["id"] for p in self._ok(
                self.alice.get("/api/people", params={"q": "СМИРНОВА"})
            )],
            [person_id],
        )
        self.assertEqual(
            self._ok(self.alice.get("/api/people", params={"q": "нет такого"})),
            [],
        )
        self.assertEqual(
            [p["id"] for p in self._ok(
                self.alice.get("/api/people", params={"tag": "семья"})
            )],
            [person_id],
        )

        # Второй пользователь не видит ни человека, ни контакты.
        self.assertNotIn(
            person_id, [p["id"] for p in self._ok(self.bob.get("/api/people"))]
        )
        self.assertEqual(self.bob.get(f"/api/people/{person_id}").status_code, 404)
        self.assertEqual(
            self.bob.get(f"/api/people/{person_id}/relations").status_code, 404
        )
        self.assertNotIn("+7 999", self.bob.get("/api/people").text)

        # Удаление человека: связи/участия/task_people уходят, событие и
        # задача остаются.
        self.assertEqual(self.alice.delete(f"/api/people/{person_id}").status_code,
                         204)
        self.assertEqual(self.alice.get(f"/api/people/{person_id}").status_code,
                         404)
        self.assertEqual(self.alice.delete(f"/api/people/{person_id}").status_code,
                         404)
        self.assertEqual(
            self._ok(self.alice.get(f"/api/events/{event['id']}/participants")), []
        )
        self.assertEqual(
            self._ok(self.alice.get(f"/api/tasks/{task['id']}/people")), []
        )
        self.assertEqual(self.alice.get(f"/api/events/{event['id']}").status_code,
                         200)
        self.assertEqual(self.alice.get(f"/api/tasks/{task['id']}").status_code,
                         200)

        with self.app.state.SessionLocal() as db:
            self.assertIsNone(db.get(Person, person_id))
            for model in (PersonSphere, PersonProject, EventParticipant,
                          TaskPerson):
                with self.subTest(model=model.__tablename__):
                    self.assertEqual(
                        db.query(model).filter_by(person_id=person_id).count(), 0
                    )
            self.assertIsNotNone(db.get(Event, event["id"]))
            self.assertIsNotNone(db.get(Task, task["id"]))

    # ---------- A5: задачи ----------

    def test_a5_tasks_pm_acceptance(self) -> None:
        parent = self._create_task(self.alice, title="Родитель")
        child = self._create_task(
            self.alice, title="Ребёнок", parent_id=parent["id"]
        )
        card = self._ok(self.alice.get(f"/api/tasks/{parent['id']}"))
        self.assertEqual([s["id"] for s in card["subtasks"]], [child["id"]])
        self.assertEqual(card["subtasks"][0]["parent_id"], parent["id"])

        # Каскад: удаление родителя удаляет подзадачу.
        self.assertEqual(
            self.alice.delete(f"/api/tasks/{parent['id']}").status_code, 204
        )
        self.assertEqual(
            self.alice.get(f"/api/tasks/{child['id']}").status_code, 404
        )

        # Блокер: в doing не пускает, после done — пускает.
        blocker = self._create_task(self.alice, title="Блокер")
        blocked = self._create_task(
            self.alice, title="Заблокирована", blocked_by=[blocker["id"]]
        )
        self.assertEqual(
            self._ok(self.alice.get(f"/api/tasks/{blocked['id']}"))["blocked_by"],
            [{"id": blocker["id"], "title": "Блокер", "status": "todo"}],
        )
        conflict = self.alice.patch(
            f"/api/tasks/{blocked['id']}", json={"status": "doing"}
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(
            conflict.json()["detail"]["blockers"][0]["id"], blocker["id"]
        )
        # Создание сразу в doing при открытом блокере — тоже 409.
        self.assertEqual(
            self.alice.post(
                "/api/tasks",
                json={"title": "Сразу doing", "status": "doing",
                      "blocked_by": [blocker["id"]]},
            ).status_code,
            409,
        )
        self._ok(
            self.alice.patch(
                f"/api/tasks/{blocker['id']}", json={"status": "done"}
            )
        )
        moved = self._ok(
            self.alice.patch(
                f"/api/tasks/{blocked['id']}", json={"status": "doing"}
            )
        )
        self.assertEqual(moved["status"], "doing")

        # RRULE: done создаёт следующий экземпляр с due_at + 1 день.
        recurring = self._create_task(
            self.alice,
            title="Ежедневная",
            rrule="FREQ=DAILY",
            due_at="2026-12-01T09:00:00",
        )
        done = self._ok(
            self.alice.patch(
                f"/api/tasks/{recurring['id']}", json={"status": "done"}
            )
        )
        self.assertEqual(done["status"], "done")
        nxt = done["next_task"]
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["status"], "todo")
        self.assertEqual(nxt["due_at"], "2026-12-02T09:00:00")
        self.assertEqual(nxt["title"], "Ежедневная")
        self.assertEqual(nxt["rrule"], "FREQ=DAILY")
        # Повторный done не плодит копии.
        self.assertIsNone(
            self._ok(
                self.alice.patch(
                    f"/api/tasks/{recurring['id']}", json={"status": "done"}
                )
            )["next_task"]
        )
        # Новый экземпляр существует и виден списком.
        self.assertEqual(
            self.alice.get(f"/api/tasks/{nxt['id']}").status_code, 200
        )

        # Доска/фильтры: status, overdue, project_id.
        sphere = self._create_sphere(self.alice, "Работа")
        project = self._create_project(self.alice, sphere["id"], "Атлас")
        overdue = self._create_task(
            self.alice, title="Просрочена", due_at="2020-01-01T00:00:00"
        )
        future = self._create_task(
            self.alice, title="Будущая", due_at="2035-01-01T00:00:00"
        )
        closed = self._create_task(
            self.alice, title="Закрытая", due_at="2020-01-01T00:00:00"
        )
        self._ok(
            self.alice.patch(
                f"/api/tasks/{closed['id']}", json={"status": "done"}
            )
        )
        in_project = self._create_task(
            self.alice, title="В проекте",
            project_id=project["id"], sphere_id=sphere["id"],
        )

        def ids(path: str, **params) -> list[int]:
            return sorted(t["id"] for t in self._ok(
                self.alice.get(path, params=params)
            ))

        self.assertEqual(ids("/api/tasks", overdue="true"), [overdue["id"]])
        # done: закрытая, блокер и исходник RRULE; todo: остальные и копия RRULE.
        self.assertEqual(
            ids("/api/tasks", status="done"),
            sorted([closed["id"], blocker["id"], recurring["id"]]),
        )
        self.assertEqual(
            ids("/api/tasks", status="todo"),
            sorted([overdue["id"], future["id"], in_project["id"], nxt["id"]]),
        )
        self.assertEqual(
            ids("/api/tasks", project_id=project["id"]), [in_project["id"]]
        )
        self.assertEqual(
            ids("/api/tasks", sphere_id=sphere["id"]), [in_project["id"]]
        )

        # Изоляция фильтров: чужой проект/сфера — 404.
        bob_sphere = self._create_sphere(self.bob, "Боб")
        bob_project = self._create_project(self.bob, bob_sphere["id"], "Боб")
        self.assertEqual(
            self.alice.get(
                "/api/tasks", params={"project_id": bob_project["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.alice.get(
                "/api/tasks", params={"sphere_id": bob_sphere["id"]}
            ).status_code,
            404,
        )

    # ---------- A6: события, .ics, подписка ----------

    def test_a6_events_ics_and_subscription(self) -> None:
        person = self._create_person(self.alice, "Гость")
        event = self._create_event(
            self.alice,
            title="Планирование Q1",
            description="Повестка",
            location="Комната 1",
        )
        self._ok(
            self.alice.post(
                f"/api/events/{event['id']}/participants",
                json={"person_id": person["id"], "role": "гость"},
            ),
            201,
        )
        self.assertEqual(
            self._ok(
                self.alice.get(f"/api/events/{event['id']}/participants")
            ),
            [{"person_id": person["id"], "role": "гость"}],
        )

        ics = self.alice.get(f"/api/events/{event['id']}.ics")
        self.assertEqual(ics.status_code, 200, ics.text)
        self.assertIn("text/calendar", ics.headers["content-type"])
        text = ics.text
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("END:VEVENT", text)
        self.assertIn("VERSION:2.0", text)
        self.assertIn(f"UID:{event['id']}@atlas", text)
        self.assertIn("SUMMARY:Планирование Q1", text)
        self.assertIn("DTSTART:20260301T100000Z", text)
        self.assertIn("DTEND:20260301T110000Z", text)

        # Чужой .ics — 404 (та же проверка, что и в матрице, здесь по факту).
        self.assertEqual(
            self.bob.get(f"/api/events/{event['id']}.ics").status_code, 404
        )

        # Повторяющееся событие: развёртывание даёт несколько вхождений.
        recurring = self._create_event(
            self.alice,
            title="Ежедневное",
            start_at="2026-03-02T09:00:00",
            end_at=None,
            rrule="FREQ=DAILY;COUNT=3",
        )
        window = {"from": "2026-03-02T00:00:00", "to": "2026-03-04T23:59:59"}
        expanded = self._ok(
            self.alice.get("/api/events", params={**window, "expand": "true"})
        )
        self.assertEqual(
            [item["start_at"] for item in expanded],
            [
                "2026-03-02T09:00:00",
                "2026-03-03T09:00:00",
                "2026-03-04T09:00:00",
            ],
        )
        self.assertTrue(all(item["occurrence"] for item in expanded))
        base = self._ok(
            self.alice.get("/api/events", params={**window, "expand": "false"})
        )
        self.assertEqual([item["id"] for item in base], [recurring["id"]])
        self.assertFalse(base[0]["occurrence"])

        # Подписка: токен, публичный GET без cookie, отзыв.
        token = self._ok(self.alice.post("/api/calendars/all/token"), 201)
        self.assertTrue(token["token"])
        self.assertIn("/api/calendars/all.ics?token=", token["url"])
        with TestClient(self.app) as anonymous:
            feed = anonymous.get(token["url"])
            self.assertEqual(feed.status_code, 200, feed.text)
            self.assertIn("text/calendar", feed.headers["content-type"])
            self.assertIn(f"UID:{event['id']}@atlas", feed.text)
            self.assertIn(f"UID:{recurring['id']}@atlas", feed.text)
            self.assertEqual(
                anonymous.get(
                    "/api/calendars/all.ics?token=wrong-token"
                ).status_code,
                404,
            )
            self.assertEqual(
                anonymous.get("/api/calendars/all.ics").status_code, 404
            )
            # Токен scope all не открывает другой scope.
            self.assertEqual(
                anonymous.get(
                    f"/api/calendars/sphere-{event['id']}.ics"
                    f"?token={token['token']}"
                ).status_code,
                404,
            )
        self.assertEqual(
            self.alice.delete("/api/calendars/all/token").status_code, 204
        )
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.get(token["url"]).status_code, 404)
        # Повторный отзыв не падает.
        self.assertEqual(
            self.alice.delete("/api/calendars/all/token").status_code, 204
        )
        # Токен на чужой scope не выписывается.
        bob_sphere = self._create_sphere(self.bob, "Боб")
        self.assertEqual(
            self.alice.post(
                f"/api/calendars/sphere-{bob_sphere['id']}/token"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.alice.post("/api/calendars/nonsense/token").status_code, 404
        )

    # ---------- Негатив и повторные действия ----------

    def test_negative_and_repeat_actions(self) -> None:
        # Неверный вход — 401, сессии нет.
        with TestClient(self.app) as anon:
            self.assertEqual(
                anon.post(
                    "/api/auth/login",
                    json={"username": "alice", "password": "wrong"},
                ).status_code,
                401,
            )
            self.assertEqual(anon.get("/api/me").status_code, 401)
            self.assertEqual(anon.get("/api/spheres").status_code, 401)

        # Пустые данные: человек без контактов, пустые списки.
        person = self._create_person(self.alice, name="Без контактов")
        self.assertEqual(person["contacts"], {})
        self.assertEqual(person["tags"], [])
        self.assertEqual(self._ok(self.alice.get("/api/people")), [person])

        # Повторная привязка обновляет роль, а не дублирует строку.
        sphere = self._create_sphere(self.alice, "Работа")
        self._ok(
            self.alice.post(
                f"/api/people/{person['id']}/spheres",
                json={"sphere_id": sphere["id"], "role": "коллега"},
            ),
            201,
        )
        self._ok(
            self.alice.post(
                f"/api/people/{person['id']}/spheres",
                json={"sphere_id": sphere["id"], "role": "руководитель"},
            ),
            201,
        )
        self.assertEqual(
            self._ok(
                self.alice.get(f"/api/people/{person['id']}/relations")
            )["spheres"],
            [{"id": sphere["id"], "name": "Работа", "role": "руководитель"}],
        )
        # Повторное удаление связи — 404.
        self.assertEqual(
            self.alice.delete(
                f"/api/people/{person['id']}/spheres/{sphere['id']}"
            ).status_code,
            204,
        )
        self.assertEqual(
            self.alice.delete(
                f"/api/people/{person['id']}/spheres/{sphere['id']}"
            ).status_code,
            404,
        )
        # Повторный POST участника/человека в задаче — обновление роли.
        event = self._create_event(self.alice)
        self._ok(
            self.alice.post(
                f"/api/events/{event['id']}/participants",
                json={"person_id": person["id"], "role": "гость"},
            ),
            201,
        )
        self._ok(
            self.alice.post(
                f"/api/events/{event['id']}/participants",
                json={"person_id": person["id"], "role": "ведущий"},
            ),
            201,
        )
        self.assertEqual(
            self._ok(
                self.alice.get(f"/api/events/{event['id']}/participants")
            ),
            [{"person_id": person["id"], "role": "ведущий"}],
        )
        task = self._create_task(self.alice, title="Задача")
        for role in ("исполнитель", "автор"):
            self._ok(
                self.alice.post(
                    f"/api/tasks/{task['id']}/people",
                    json={"person_id": person["id"], "role": role},
                )
            )
        self.assertEqual(
            self._ok(self.alice.get(f"/api/tasks/{task['id']}/people")),
            [{"person_id": person["id"], "name": "Без контактов",
              "role": "автор"}],
        )
        # Невалидный RRULE и пустое имя — 422.
        self.assertEqual(
            self.alice.post(
                "/api/tasks", json={"title": "x", "rrule": "FREQ=NOPE"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.alice.post("/api/people", json={"name": "   "}).status_code, 422
        )
        self.assertEqual(
            self.alice.get(f"/api/events/{event['id']}/participants").status_code,
            200,
        )

        # Выход гасит сессию: тот же клиент дальше — 401.
        self.assertEqual(self.alice.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.alice.get("/api/spheres").status_code, 401)
        self.assertEqual(self.alice.get(f"/api/people/{person['id']}").status_code,
                         401)


if __name__ == "__main__":
    unittest.main()
