"""Диагностика: какие события дают напоминание в упавшем тесте test_push.

Повторяет три события из test_rrule_weekno_yearday_density_and_expand_limit
и печатает вердикт плотности + созданные уведомления. Ничего не меняет в app.
"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.backend.db import Base
from app.backend.main import create_app
from app.backend import pm
from app.backend.models import Event, Notification, User
from app.backend.reminders import dispatch_due

weekno = (
    "FREQ=YEARLY;BYWEEKNO="
    + ",".join(str(i) for i in range(1, 54))
    + ";BYDAY=MO,TU,WE,TH,FR,SA,SU"
)
yearday = (
    "FREQ=YEARLY;BYYEARDAY="
    + ",".join(str(i) for i in range(1, 37))
    + ";BYHOUR="
    + ",".join(str(i) for i in range(24))
)
now = datetime.now()
upper = now + timedelta(minutes=15)

for title, rrule in (("BYWEEKNO 53x7", weekno), ("BYYEARDAY x BYHOUR", yearday)):
    print(
        f"{title}: too_dense={pm.rrule_too_dense(rrule, datetime(2020, 1, 1), upper)}"
    )

tmp = tempfile.TemporaryDirectory()
url = f"sqlite:///{(Path(tmp.name) / 'diag.db').as_posix()}"
app = create_app(url)
Base.metadata.create_all(app.state.engine)
with app.state.SessionLocal() as db:
    user = User(username="diag", password_hash="x")
    db.add(user)
    db.commit()
    db.add_all(
        [
            Event(
                owner_id=user.id,
                title="BYWEEKNO 53x7",
                start_at=datetime(2020, 1, 1),
                remind_minutes=15,
                rrule=weekno,
            ),
            Event(
                owner_id=user.id,
                title="BYYEARDAY x BYHOUR",
                start_at=datetime(2020, 1, 1),
                remind_minutes=15,
                rrule=yearday,
            ),
            Event(
                owner_id=user.id,
                title="Valid DAILY",
                start_at=now + timedelta(minutes=10),
                remind_minutes=15,
                rrule="FREQ=DAILY",
            ),
        ]
    )
    db.commit()

print("now:", now.isoformat())
with app.state.SessionLocal() as db:
    created = dispatch_due(db, now)
    rows = db.query(Notification).all()
print("created:", created)
for row in rows:
    print("notification:", row.title, "|", row.dedupe_key)

app.state.engine.dispose()
tmp.cleanup()
