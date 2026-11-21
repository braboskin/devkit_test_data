"""FR-9: события, повторения, участники, `.ics` и подписка на календарь."""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.auth import hash_password
from app.backend.db import Base
from app.backend.main import create_app
from app.backend.models import Event, Person, Project, Sphere, User

ALICE = {"username": "alice", "password": "alice-pass"}
BOB = {"username": "bob", "password": "bob-pass"}

EVENT = {
    "title": "Planning",
    "start_at": "2026-03-01T10:00:00",
    "end_at": "2026-03-01T11:00:00",
}


class EventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{(Path(self.tmp.name) / 'test.db').as_posix()}"
        self.app = create_app(self.url)
        self.engine = self.app.state.engine
        Base.metadata.create_all(self.engine)
        with self.app.state.SessionLocal() as db:
            self.alice = User(
                username=ALICE["username"],
                password_hash=hash_password(ALICE["password"]),
            )
            self.bob = User(
                username=BOB["username"],
                password_hash=hash_password(BOB["password"]),
            )
            db.add_all([self.alice, self.bob])
            db.commit()
            self.alice_sphere = Sphere(owner_id=self.alice.id, name="Work")
            self.bob_sphere = Sphere(owner_id=self.bob.id, name="Home")
            db.add_all([self.alice_sphere, self.bob_sphere])
            db.commit()
            self.alice_project = Project(
                owner_id=self.alice.id,
                sphere_id=self.alice_sphere.id,
                name="Atlas",
            )
            self.bob_project = Project(
                owner_id=self.bob.id,
                sphere_id=self.bob_sphere.id,
                name="Other",
            )
            self.alice_person = Person(owner_id=self.alice.id, name="Carol")
            self.bob_person = Person(owner_id=self.bob.id, name="Dave")
            db.add_all(
                [
                    self.alice_project,
                    self.bob_project,
                    self.alice_person,
                    self.bob_person,
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

    def test_requires_session(self) -> None:
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/events").status_code, 401)
            self.assertEqual(client.post("/api/events", json=EVENT).status_code, 401)

    def test_crud_event(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = client.post(
                "/api/events",
                json={
                    **EVENT,
                    "sphere_id": self.alice_sphere.id,
                    "project_id": self.alice_project.id,
                    "location": "Room 1",
                    "description": "Sync",
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            event_id = created.json()["id"]
            self.assertEqual(created.json()["sphere_id"], self.alice_sphere.id)

            listed = client.get("/api/events")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual([item["id"] for item in listed.json()], [event_id])
            self.assertFalse(listed.json()[0]["occurrence"])

            got = client.get(f"/api/events/{event_id}")
            self.assertEqual(got.status_code, 200)
            self.assertEqual(got.json()["title"], "Planning")

            patched = client.patch(
                f"/api/events/{event_id}",
                json={"title": "Renamed", "location": None},
            )
            self.assertEqual(patched.status_code, 200, patched.text)
            self.assertEqual(patched.json()["title"], "Renamed")
            self.assertIsNone(patched.json()["location"])

            deleted = client.delete(f"/api/events/{event_id}")
            self.assertEqual(deleted.status_code, 204)
            self.assertEqual(client.get(f"/api/events/{event_id}").status_code, 404)

    def test_validation(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            self.assertEqual(
                client.post("/api/events", json={"title": "no start"}).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/events",
                    json={**EVENT, "end_at": "2026-02-28T10:00:00"},
                ).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/events", json={**EVENT, "rrule": "FREQ=WRONG"}
                ).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/events", json={**EVENT, "remind_minutes": -1}
                ).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/events",
                    json={**EVENT, "sphere_id": self.bob_sphere.id},
                ).status_code,
                404,
            )
            self.assertEqual(
                client.post(
                    "/api/events",
                    json={**EVENT, "project_id": self.bob_project.id},
                ).status_code,
                404,
            )

            all_day = client.post(
                "/api/events",
                json={**EVENT, "all_day": True, "end_at": None},
            )
            self.assertEqual(all_day.status_code, 201, all_day.text)
            self.assertTrue(all_day.json()["all_day"])

            event_id = all_day.json()["id"]
            bad_patch = client.patch(
                f"/api/events/{event_id}",
                json={"start_at": "2026-03-02T10:00:00"},
            )
            # end_at не задан — переносить можно; ошибка только при end_at < start_at
            self.assertEqual(bad_patch.status_code, 200, bad_patch.text)
            conflicting = client.patch(
                f"/api/events/{event_id}",
                json={
                    "start_at": "2026-03-05T10:00:00",
                    "end_at": "2026-03-04T10:00:00",
                },
            )
            self.assertEqual(conflicting.status_code, 422)

    def test_event_ics(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = client.post(
                "/api/events",
                json={
                    "title": "Planning; sync, review",
                    "start_at": "2026-03-01T10:00:00",
                    "end_at": "2026-03-01T11:00:00",
                    "location": "Room 1; floor 2",
                    "description": "Line1\nLine2",
                    "rrule": "FREQ=DAILY;COUNT=3",
                },
            ).json()
            response = client.get(f"/api/events/{created['id']}.ics")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/calendar", response.headers["content-type"])
            text = response.text
            self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
            self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
            self.assertNotIn("\n", text.replace("\r\n", ""))
            self.assertIn("VERSION:2.0", text)
            self.assertIn("PRODID:-//Atlas//RU", text)
            self.assertIn("BEGIN:VEVENT", text)
            self.assertIn("END:VEVENT", text)
            self.assertIn(f"UID:{created['id']}@atlas", text)
            self.assertIn("SUMMARY:Planning\\; sync\\, review", text)
            self.assertIn("LOCATION:Room 1\\; floor 2", text)
            self.assertIn("DESCRIPTION:Line1\\nLine2", text)
            self.assertIn("DTSTART:20260301T100000Z", text)
            self.assertIn("DTEND:20260301T110000Z", text)
            self.assertIn("RRULE:FREQ=DAILY;COUNT=3", text)
            self.assertRegex(text, r"DTSTAMP:\d{8}T\d{6}Z")

            all_day = client.post(
                "/api/events",
                json={
                    "title": "Holiday",
                    "start_at": "2026-03-05T00:00:00",
                    "all_day": True,
                },
            ).json()
            all_day_text = client.get(f"/api/events/{all_day['id']}.ics").text
            self.assertIn("DTSTART;VALUE=DATE:20260305", all_day_text)
            self.assertIn("DTEND;VALUE=DATE:20260306", all_day_text)

    def test_all_day_dtend_is_exclusive(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)

            def dtend(payload: dict) -> str:
                created = client.post("/api/events", json=payload)
                self.assertEqual(created.status_code, 201, created.text)
                text = client.get(f"/api/events/{created.json()['id']}.ics").text
                lines = [
                    line
                    for line in text.split("\r\n")
                    if line.startswith("DTEND")
                ]
                self.assertEqual(len(lines), 1, text)
                return lines[0]

            # end_at в API включительный: однодневное событие → +1 день.
            self.assertEqual(
                dtend(
                    {
                        "title": "One day",
                        "start_at": "2026-03-01T00:00:00",
                        "end_at": "2026-03-01T00:00:00",
                        "all_day": True,
                    }
                ),
                "DTEND;VALUE=DATE:20260302",
            )
            # Многодневное включительное: последний день 03-03 → 03-04.
            self.assertEqual(
                dtend(
                    {
                        "title": "Three days",
                        "start_at": "2026-03-01T00:00:00",
                        "end_at": "2026-03-03T00:00:00",
                        "all_day": True,
                    }
                ),
                "DTEND;VALUE=DATE:20260304",
            )
            # Без end_at — ровно один день: start + 1.
            self.assertEqual(
                dtend(
                    {
                        "title": "No end",
                        "start_at": "2026-03-01T00:00:00",
                        "all_day": True,
                    }
                ),
                "DTEND;VALUE=DATE:20260302",
            )

    def test_ics_folding(self) -> None:
        description = "Длинное описание встречи с кириллицей " * 8
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = client.post(
                "/api/events",
                json={
                    "title": "Fold",
                    "start_at": "2026-03-01T10:00:00",
                    "end_at": "2026-03-01T11:00:00",
                    "description": description,
                },
            ).json()
            response = client.get(f"/api/events/{created['id']}.ics")
            self.assertEqual(response.status_code, 200)
            raw = response.content
            physical = raw.split(b"\r\n")
            self.assertTrue(len(physical) > 3)
            for line in physical:
                self.assertLessEqual(len(line), 75, line)
            self.assertIn(b"\r\n ", raw)
            # Одиночных LF, не входящих в CRLF, быть не должно.
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            text = response.text
            self.assertNotIn("\n", text.replace("\r\n", ""))
            # Разворачивание возвращает исходный content-line (UTF-8 цел).
            unfolded = text.replace("\r\n ", "")
            description_lines = [
                line
                for line in unfolded.split("\r\n")
                if line.startswith("DESCRIPTION:")
            ]
            self.assertEqual(description_lines, [f"DESCRIPTION:{description}"])
            self.assertIn("SUMMARY:Fold\r\n", text)

    def test_rrule_normalized(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = client.post(
                "/api/events",
                json={
                    "title": "Prefixed",
                    "start_at": "2026-03-02T09:00:00",
                    "rrule": "RRULE:FREQ=DAILY",
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(created.json()["rrule"], "FREQ=DAILY")
            event_id = created.json()["id"]

            got = client.get(f"/api/events/{event_id}")
            self.assertEqual(got.json()["rrule"], "FREQ=DAILY")
            with self.app.state.SessionLocal() as db:
                self.assertEqual(db.get(Event, event_id).rrule, "FREQ=DAILY")

            text = client.get(f"/api/events/{event_id}.ics").text
            self.assertEqual(text.count("RRULE:FREQ=DAILY"), 1, text)
            self.assertNotIn("RRULE:RRULE:", text)

            # trim и регистронезависимый префикс
            trimmed = client.post(
                "/api/events",
                json={
                    **EVENT,
                    "rrule": "  rrule:FREQ=WEEKLY;COUNT=2  ",
                },
            )
            self.assertEqual(trimmed.status_code, 201, trimmed.text)
            self.assertEqual(trimmed.json()["rrule"], "FREQ=WEEKLY;COUNT=2")

            patched = client.patch(
                f"/api/events/{event_id}",
                json={"rrule": "RRULE:FREQ=MONTHLY"},
            )
            self.assertEqual(patched.status_code, 200, patched.text)
            self.assertEqual(patched.json()["rrule"], "FREQ=MONTHLY")
            self.assertNotIn(
                "RRULE:RRULE:", client.get(f"/api/events/{event_id}.ics").text
            )

            # Старая запись БД с префиксом: ICS всё равно с одним RRULE.
            with self.app.state.SessionLocal() as db:
                db.get(Event, event_id).rrule = "RRULE:FREQ=DAILY;COUNT=2"
                db.commit()
            legacy = client.get(f"/api/events/{event_id}.ics").text
            self.assertEqual(legacy.count("RRULE:FREQ=DAILY;COUNT=2"), 1, legacy)
            self.assertNotIn("RRULE:RRULE:", legacy)

            for bad in (
                "FREQ=DAILY\nCOUNT=3",
                "FREQ=DAILY\r\n",
                "   ",
                "",
                "RRULE:",
            ):
                self.assertEqual(
                    client.post(
                        "/api/events", json={**EVENT, "rrule": bad}
                    ).status_code,
                    422,
                    bad,
                )
                self.assertEqual(
                    client.patch(
                        f"/api/events/{event_id}", json={"rrule": bad}
                    ).status_code,
                    422,
                    bad,
                )

            # Повторяемость после нормализации не сломана.
            expanded = client.get(
                "/api/events",
                params={
                    "from": "2026-03-02T00:00:00",
                    "to": "2026-03-03T23:59:59",
                },
            )
            self.assertEqual(expanded.status_code, 200)
            self.assertEqual(len(expanded.json()), 2, expanded.json())

    def test_recurrence_expand(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            created = client.post(
                "/api/events",
                json={
                    "title": "Daily",
                    "start_at": "2026-03-02T09:00:00",
                    "rrule": "FREQ=DAILY;COUNT=3",
                },
            )
            self.assertEqual(created.status_code, 201, created.text)

            window = {"from": "2026-03-02T00:00:00", "to": "2026-03-04T23:59:59"}
            expanded = client.get("/api/events", params=window)
            self.assertEqual(expanded.status_code, 200)
            items = expanded.json()
            self.assertEqual(len(items), 3, items)
            self.assertTrue(all(item["occurrence"] for item in items))
            self.assertEqual(
                [item["start_at"] for item in items],
                [
                    "2026-03-02T09:00:00",
                    "2026-03-03T09:00:00",
                    "2026-03-04T09:00:00",
                ],
            )

            base = client.get(
                "/api/events", params={**window, "expand": "false"}
            )
            self.assertEqual(base.status_code, 200)
            self.assertEqual(len(base.json()), 1)
            self.assertFalse(base.json()[0]["occurrence"])

            plain = client.get("/api/events")
            self.assertEqual(len(plain.json()), 1)

            one_day = client.get(
                "/api/events",
                params={
                    "from": "2026-03-03T00:00:00",
                    "to": "2026-03-03T23:59:59",
                },
            )
            self.assertEqual(
                [item["start_at"] for item in one_day.json()],
                ["2026-03-03T09:00:00"],
            )

            self.assertEqual(
                client.get(
                    "/api/events",
                    params={
                        "from": "2026-03-02T00:00:00",
                        "expand": "true",
                    },
                ).status_code,
                422,
            )

    def test_participants(self) -> None:
        with TestClient(self.app) as client:
            self._login(client, ALICE)
            event_id = client.post("/api/events", json=EVENT).json()["id"]

            added = client.post(
                f"/api/events/{event_id}/participants",
                json={"person_id": self.alice_person.id, "role": "owner"},
            )
            self.assertEqual(added.status_code, 201, added.text)
            self.assertEqual(
                added.json(),
                {"person_id": self.alice_person.id, "role": "owner"},
            )

            listed = client.get(f"/api/events/{event_id}/participants")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(len(listed.json()), 1)
            self.assertEqual(listed.json()[0]["person_id"], self.alice_person.id)

            foreign = client.post(
                f"/api/events/{event_id}/participants",
                json={"person_id": self.bob_person.id},
            )
            self.assertEqual(foreign.status_code, 404)

            removed = client.delete(
                f"/api/events/{event_id}/participants/{self.alice_person.id}"
            )
            self.assertEqual(removed.status_code, 204)
            self.assertEqual(
                client.get(f"/api/events/{event_id}/participants").json(), []
            )
            self.assertEqual(
                client.delete(
                    f"/api/events/{event_id}/participants/{self.alice_person.id}"
                ).status_code,
                404,
            )

    def test_subscription(self) -> None:
        with TestClient(self.app) as alice:
            self._login(alice, ALICE)
            event_id = alice.post(
                "/api/events", json={**EVENT, "sphere_id": self.alice_sphere.id}
            ).json()["id"]

            token = alice.post("/api/calendars/all/token")
            self.assertEqual(token.status_code, 201, token.text)
            body = token.json()
            self.assertTrue(body["token"])
            self.assertIn("/api/calendars/all.ics?token=", body["url"])

            with TestClient(self.app) as anonymous:
                feed = anonymous.get(body["url"])
                self.assertEqual(feed.status_code, 200)
                self.assertIn("text/calendar", feed.headers["content-type"])
                self.assertIn(f"UID:{event_id}@atlas", feed.text)
                self.assertEqual(
                    anonymous.get(
                        "/api/calendars/all.ics?token=wrong-token"
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    anonymous.get("/api/calendars/all.ics").status_code, 404
                )
                self.assertEqual(
                    anonymous.get(
                        f"/api/calendars/sphere-{self.alice_sphere.id}.ics"
                        f"?token={body['token']}"
                    ).status_code,
                    404,
                )

            # Новый токен заменяет прежний для того же scope.
            replaced = alice.post("/api/calendars/all/token").json()
            with TestClient(self.app) as anonymous:
                self.assertEqual(anonymous.get(body["url"]).status_code, 404)
                self.assertEqual(anonymous.get(replaced["url"]).status_code, 200)

            self.assertEqual(
                alice.post(
                    f"/api/calendars/sphere-{self.bob_sphere.id}/token"
                ).status_code,
                404,
            )
            self.assertEqual(
                alice.post(
                    f"/api/calendars/project-{self.bob_project.id}/token"
                ).status_code,
                404,
            )
            self.assertEqual(
                alice.post("/api/calendars/nonsense/token").status_code, 404
            )

            sphere_token = alice.post(
                f"/api/calendars/sphere-{self.alice_sphere.id}/token"
            )
            self.assertEqual(sphere_token.status_code, 201, sphere_token.text)
            with TestClient(self.app) as anonymous:
                scoped = anonymous.get(sphere_token.json()["url"])
                self.assertEqual(scoped.status_code, 200)
                self.assertIn(f"UID:{event_id}@atlas", scoped.text)

            revoked = alice.delete("/api/calendars/all/token")
            self.assertEqual(revoked.status_code, 204)
            with TestClient(self.app) as anonymous:
                self.assertEqual(anonymous.get(replaced["url"]).status_code, 404)

    def test_isolation(self) -> None:
        with TestClient(self.app) as alice, TestClient(self.app) as bob:
            self._login(alice, ALICE)
            self._login(bob, BOB)

            event_id = alice.post("/api/events", json=EVENT).json()["id"]

            self.assertEqual(bob.get("/api/events").json(), [])
            self.assertEqual(bob.get(f"/api/events/{event_id}").status_code, 404)
            self.assertEqual(
                bob.get(f"/api/events/{event_id}.ics").status_code, 404
            )
            self.assertEqual(
                bob.patch(
                    f"/api/events/{event_id}", json={"title": "hacked"}
                ).status_code,
                404,
            )
            self.assertEqual(
                bob.delete(f"/api/events/{event_id}").status_code, 404
            )
            self.assertEqual(
                bob.post(
                    f"/api/events/{event_id}/participants",
                    json={"person_id": self.bob_person.id},
                ).status_code,
                404,
            )
            self.assertEqual(
                alice.get(
                    "/api/events", params={"sphere_id": self.bob_sphere.id}
                ).status_code,
                404,
            )
            self.assertEqual(
                alice.get(
                    "/api/events", params={"project_id": self.bob_project.id}
                ).status_code,
                404,
            )

            own_event = bob.post("/api/events", json=EVENT).json()
            self.assertEqual(
                bob.post(
                    f"/api/events/{own_event['id']}/participants",
                    json={"person_id": self.alice_person.id},
                ).status_code,
                404,
            )
            self.assertEqual(
                [item["id"] for item in bob.get("/api/events").json()],
                [own_event["id"]],
            )


if __name__ == "__main__":
    unittest.main()
