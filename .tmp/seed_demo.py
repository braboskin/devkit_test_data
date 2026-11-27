"""Демо-данные для стенда: alice наполняется, bob вычищается до первого входа.

Скрипт одноразовый, живёт в .tmp (в git не попадает).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(r"X:\devkit_projects\projects\atlas\repo\atlas")
sys.path.insert(0, str(ROOT))

from app.backend.core.security import hash_password  # noqa: E402

DB = Path(r"X:\devkit_projects\projects\atlas\.secrets\atlas.db")
BASE = "http://127.0.0.1:8000"
ALICE_PW = "Atlas-Alice-2026"
BOB_PW = "Atlas-Bob-2026"


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso(days: float, hour: int = 10, minute: int = 0) -> str:
    value = (now() + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def reset_passwords() -> tuple[str, str]:
    con = sqlite3.connect(DB)
    con.execute(
        "update users set password_hash=? where username='alice'", (hash_password(ALICE_PW),)
    )
    con.execute(
        "update users set password_hash=? where username='bob'", (hash_password(BOB_PW),)
    )
    con.commit()
    alice_id = con.execute("select id from users where username='alice'").fetchone()[0]
    bob_id = con.execute("select id from users where username='bob'").fetchone()[0]
    con.close()
    return alice_id, bob_id


def wipe(owner_id: str, *, keep_integrations: bool) -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")

    def q(sql: str, params: tuple = ()) -> None:
        try:
            con.execute(sql, params)
        except sqlite3.Error as exc:  # noqa: BLE001
            print("skip:", sql[:60], exc)

    owner_tables = []
    for (table,) in con.execute(
        "select name from sqlite_master where type='table'"
    ).fetchall():
        cols = [c[1] for c in con.execute(f"pragma table_info({table})")]
        if "owner_id" in cols:
            owner_tables.append(table)

    # Дочерние таблицы — до родительских.
    q("delete from chunks where document_id in (select id from documents where owner_id=?)", (owner_id,))
    q("delete from messages where chat_id in (select id from chats where owner_id=?)", (owner_id,))
    q("delete from task_dependencies where task_id in (select id from tasks where owner_id=?)", (owner_id,))
    q("delete from task_dependencies where blocked_by_id in (select id from tasks where owner_id=?)", (owner_id,))
    q("delete from task_people where task_id in (select id from tasks where owner_id=?)", (owner_id,))
    q("delete from person_projects where person_id in (select id from people where owner_id=?)", (owner_id,))
    q("delete from person_spheres where person_id in (select id from people where owner_id=?)", (owner_id,))
    q("delete from event_participants where event_id in (select id from events where owner_id=?)", (owner_id,))
    q("delete from habit_logs where habit_id in (select id from habits where owner_id=?)", (owner_id,))
    q("delete from metric_entries where metric_id in (select id from metrics where owner_id=?)", (owner_id,))

    order = [
        "task_dependencies", "task_people", "event_participants",
        "person_spheres", "person_projects", "habit_logs", "metric_entries",
        "messages", "chunks", "proposals", "agent_calls", "agent_grants",
        "scenarios", "agents", "tasks", "events", "goals", "documents",
        "chats", "people", "projects", "spheres", "habits", "metrics",
        "growth_settings", "notifications", "push_subscriptions",
        "notification_settings", "onboarding_sessions", "user_profile",
        "journal_entries", "reviews", "integrations", "llm_credentials",
        "sessions",
    ]
    for table in order:
        if table not in owner_tables:
            continue
        if keep_integrations and table in {"integrations", "llm_credentials"}:
            continue
        q(f"delete from {table} where owner_id=?", (owner_id,))
    for table in owner_tables:
        if table in order:
            continue
        q(f"delete from {table} where owner_id=?", (owner_id,))

    # Осиротевшие дочерние строки без owner_id.
    q("delete from chunks where document_id not in (select id from documents)")
    q("delete from messages where chat_id not in (select id from chats)")
    q("delete from task_dependencies where task_id not in (select id from tasks) or blocked_by_id not in (select id from tasks)")
    q("delete from task_people where task_id not in (select id from tasks)")
    q("delete from person_projects where person_id not in (select id from people) or project_id not in (select id from projects)")
    q("delete from person_spheres where person_id not in (select id from people) or sphere_id not in (select id from spheres)")
    q("delete from event_participants where event_id not in (select id from events) or person_id not in (select id from people)")
    q("delete from habit_logs where habit_id not in (select id from habits)")
    q("delete from metric_entries where metric_id not in (select id from metrics)")

    con.commit()
    con.close()


def login(username: str, password: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{BASE}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if response.status_code != 200:
        raise SystemExit(f"login {username} failed: {response.status_code} {response.text}")
    return session


def post(session: requests.Session, path: str, payload: dict) -> dict:
    response = session.post(f"{BASE}{path}", json=payload, timeout=15)
    if response.status_code >= 400:
        raise SystemExit(f"POST {path} {response.status_code}: {response.text}")
    return response.json()


def put(session: requests.Session, path: str, payload: dict) -> dict:
    response = session.put(f"{BASE}{path}", json=payload, timeout=15)
    if response.status_code >= 400:
        raise SystemExit(f"PUT {path} {response.status_code}: {response.text}")
    return response.json()


def seed_alice(session: requests.Session) -> None:
    put(
        session,
        "/api/profile",
        {
            "data": {
                "onboarding_done": True,
                "onboarding_skipped": False,
                "context": {
                    "name": "Алиса",
                    "age": "29",
                    "city": "Москва",
                    "profession": "продакт-менеджер",
                    "agent": True,
                },
                "agent": {"tone": "кратко", "depth": "обычная"},
                "privacy": {"sensitive": ["медицина"]},
            },
            "summary": "Продакт-менеджер, ведёт Atlas; следит за здоровьем и финансами.",
        },
    )

    spheres: dict[str, int] = {}
    for name, color, description in [
        ("Здоровье", "#22c55e", "Сон, движение, питание"),
        ("Работа", "#3b82f6", "Atlas и карьерные цели"),
        ("Финансы", "#f59e0b", "Подушка и расходы"),
        ("Отношения", "#ec4899", "Семья, друзья, коллеги"),
        ("Дом", "#8b5cf6", "Быт и уют"),
    ]:
        body = post(session, "/api/spheres", {"name": name})
        spheres[name] = body["id"]
        # цвет/описание — отдельным PATCH (если доступен)
        session.patch(
            f"{BASE}/api/spheres/{body['id']}",
            json={"color": color, "description": description},
            timeout=10,
        )

    projects: dict[str, int] = {}
    for name, sphere_id, description, due in [
        ("Atlas: переработка интерфейса", spheres["Работа"], "Новый UI, дизайн-система, календарь", iso(45)),
        ("Марафон 10 км", spheres["Здоровье"], "Подготовка к забегу", iso(60)),
        ("Финансовая подушка", spheres["Финансы"], "Накопить 300 тыс.", iso(120)),
    ]:
        body = post(
            session,
            "/api/projects",
            {
                "sphere_id": sphere_id,
                "name": name,
                "description": description,
                "status": "active",
                "due_at": due,
            },
        )
        projects[name] = body["id"]

    people: dict[str, int] = {}
    for name, relation, notes, contacts in [
        ("Анна Петрова", "коллега", "Дизайнер Atlas, встречаемся по средам", {"telegram": "@anna_p"}),
        ("Игорь Смирнов", "друг", "Бегаем вместе по субботам", {"phone": "+7 900 000-00-01"}),
        ("Мария Ковалёва", "коллега", "Продакт в соседней команде", {"email": "maria@example.com"}),
        ("Дмитрий Орлов", "врач", "Терапевт, раз в полгода", {"phone": "+7 900 000-00-02"}),
    ]:
        body = post(
            session,
            "/api/people",
            {"name": name, "relation": relation, "notes": notes, "contacts": contacts},
        )
        people[name] = body["id"]

    tasks = [
        ("Собрать макеты календаря", "Atlas: переработка интерфейса", "done", "high", -6, 100),
        ("Дерево сфер и проектов", "Atlas: переработка интерфейса", "done", "medium", -4, 100),
        ("Страница файлов: фильтры", "Atlas: переработка интерфейса", "doing", "high", 2, 60),
        ("Гант: drag и resize", "Atlas: переработка интерфейса", "todo", "medium", 5, 0),
        ("Ревью дизайн-системы с Анной", "Atlas: переработка интерфейса", "todo", "high", 1, 0),
        ("Тренировка: интервалы 6x400", "Марафон 10 км", "doing", "medium", 0, 40),
        ("Длинная пробежка 8 км", "Марафон 10 км", "todo", "medium", 3, 0),
        ("Записаться к стоматологу", None, "todo", "low", 7, 0),
        ("Отложить 20 тыс. на подушку", "Финансовая подушка", "todo", "high", 10, 0),
        ("Разобрать расходы за месяц", "Финансовая подушка", "done", "low", -2, 100),
    ]
    for title, project_name, status, priority, due_days, progress in tasks:
        project_id = projects.get(project_name) if project_name else None
        sphere_id = (
            spheres["Работа"]
            if project_name == "Atlas: переработка интерфейса"
            else spheres["Здоровье"]
            if project_name == "Марафон 10 км"
            else spheres["Финансы"]
            if project_name == "Финансовая подушка"
            else None
        )
        post(
            session,
            "/api/tasks",
            {
                "title": title,
                "project_id": project_id,
                "sphere_id": sphere_id,
                "status": status,
                "priority": priority,
                "due_at": iso(due_days, 18),
                "start_at": iso(due_days - 2, 9),
                "progress": progress,
            },
        )

    events = [
        ("Созвон по Atlas", 0, 11, 12, "Работа", "Atlas: переработка интерфейса", None, 10),
        ("Тренировка", 0, 19, 20, "Здоровье", "Марафон 10 км", None, 30),
        ("Дизайн-ревью", 1, 15, 16, "Работа", "Atlas: переработка интерфейса", None, 15),
        ("Ужин с Анной", 2, 19, 21, "Отношения", None, None, 60),
        ("Обзор недели", 5, 19, 20, "Работа", None, "FREQ=WEEKLY;BYDAY=SU", 10),
    ]
    for title, day, h1, h2, sphere_name, project_name, rrule, remind in events:
        post(
            session,
            "/api/events",
            {
                "title": title,
                "start_at": iso(day, h1),
                "end_at": iso(day, h2),
                "all_day": False,
                "sphere_id": spheres[sphere_name],
                "project_id": projects.get(project_name) if project_name else None,
                "rrule": rrule,
                "remind_minutes": remind,
            },
        )

    for title, target, current, sphere, project, criteria in [
        ("Выпустить переработку интерфейса", 100, 40, "Работа", "Atlas: переработка интерфейса", "Все экраны в новом UI"),
        ("Пробежать 10 км", 1, 0, "Здоровье", "Марафон 10 км", "Без остановок"),
        ("Подушка 300 тыс.", 300000, 120000, "Финансы", "Финансовая подушка", "Рубли на счёте"),
    ]:
        post(
            session,
            "/api/goals",
            {
                "title": title,
                "target": target,
                "current": current,
                "criteria": criteria,
                "due_at": iso(90),
                "status": "active",
                "sphere_id": spheres[sphere],
                "project_id": projects[project],
            },
        )

    for title, cadence, target in [
        ("сон 7–8 часов", "daily", 1),
        ("8k шагов", "daily", 1),
        ("чтение 20 минут", "daily", 1),
    ]:
        post(session, "/api/habits", {"title": title, "cadence": cadence, "target_per_period": target})

    metrics: dict[str, int] = {}
    for name, unit, cadence in [
        ("вес", "кг", "daily"),
        ("шаги", "шт", "daily"),
        ("пульс покоя", "уд/мин", "daily"),
    ]:
        body = post(session, "/api/metrics", {"name": name, "kind": "number", "unit": unit, "cadence": cadence})
        metrics[name] = body["id"]

    import random

    rng = random.Random(42)
    for name, base, spread in [("вес", 78.4, 0.8), ("шаги", 8600, 2200), ("пульс покоя", 58, 4)]:
        for days_ago in range(13, -1, -1):
            value = base + rng.uniform(-spread, spread)
            session.post(
                f"{BASE}/api/metrics/{metrics[name]}/entries",
                json={"ts": iso(-days_ago, 21), "value": round(value, 1)},
                timeout=10,
            )

    put(
        session,
        "/api/growth/settings",
        {
            "daily_enabled": True,
            "daily_at": "08:00",
            "weekly_enabled": True,
            "weekly_at": "19:00",
            "weekly_day": 6,
            "triage_enabled": True,
            "audit_enabled": True,
            "nudge_enabled": True,
        },
    )

    # Документы (воркер обработает в фоне).
    for name, text, sphere in [
        ("План переработки UI.md", "# План\n\n1. Дизайн-система\n2. Календарь\n3. Файлы\n", "Работа"),
        ("Итоги недели.md", "# Итоги\n\nСделано: календарь, файлы, гант.\n", "Работа"),
    ]:
        session.post(
            f"{BASE}/api/documents",
            files={"file": (name, text.encode("utf-8"), "text/markdown")},
            data={"sphere_id": str(spheres[sphere])},
            timeout=20,
        )

    # Пара чатов-заглушек (без LLM): только создания бесед.
    for title in ["Atlas: вопросы по календарю", "Идеи для забега"]:
        session.post(f"{BASE}/api/chats", json={"title": title}, timeout=10)


def seed_bob_empty(session: requests.Session) -> None:
    # Профиль пустой -> при входе откроется мастер настройки.
    put(session, "/api/profile", {"data": {}, "summary": None})


def report(session: requests.Session, label: str) -> None:
    paths = {
        "spheres": "/api/spheres",
        "projects": "/api/projects",
        "tasks": "/api/tasks",
        "people": "/api/people",
        "events": "/api/events",
        "goals": "/api/goals",
        "habits": "/api/habits",
        "metrics": "/api/metrics",
        "documents": "/api/documents",
        "chats": "/api/chats",
    }
    parts = []
    for name, path in paths.items():
        response = session.get(f"{BASE}{path}", timeout=10)
        if response.status_code != 200:
            parts.append(f"{name}=ERR{response.status_code}")
            continue
        parts.append(f"{name}={len(response.json())}")
    profile = session.get(f"{BASE}/api/profile", timeout=10).json()
    parts.append(f"profile_keys={sorted((profile.get('data') or {}).keys())}")
    print(label, " ".join(parts))


def main() -> None:
    alice_id, bob_id = reset_passwords()
    print("passwords reset")

    wipe(alice_id, keep_integrations=True)
    print("alice wiped")
    alice = login("alice", ALICE_PW)
    seed_alice(alice)
    print("alice seeded")

    wipe(bob_id, keep_integrations=False)
    print("bob wiped")
    bob = login("bob", BOB_PW)
    seed_bob_empty(bob)
    print("bob empty profile")

    report(alice, "ALICE")
    report(bob, "BOB")


if __name__ == "__main__":
    main()
