"""Ручная генерация iCalendar (RFC 5545) без внешних зависимостей."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

FOLD_LIMIT = 75


def _escape(text: str) -> str:
    """Экранирование TEXT-полей RFC 5545: `\\`, `;`, `,`, переводы строк."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _utc_stamp(value: datetime) -> str:
    return _naive_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _date_stamp(value: datetime) -> str:
    return _naive_utc(value).strftime("%Y%m%d")


def _chunk(raw: bytes, limit: int) -> bytes:
    """Отрезать не больше `limit` октетов, не разрывая символ UTF-8."""
    if len(raw) <= limit:
        return raw
    end = limit
    while end > 0 and (raw[end] & 0xC0) == 0x80:
        end -= 1
    return raw[:end]


def _fold(line: str) -> list[str]:
    """Сложить content-line по RFC 5545: ≤75 октетов, продолжение с пробела."""
    raw = line.encode("utf-8")
    if len(raw) <= FOLD_LIMIT:
        return [line]
    head = _chunk(raw, FOLD_LIMIT)
    folded = [head.decode("utf-8")]
    raw = raw[len(head):]
    while raw:
        # Продолжение: ведущий пробел + до 74 октетов = 75 в строке.
        chunk = _chunk(raw, FOLD_LIMIT - 1)
        folded.append(" " + chunk.decode("utf-8"))
        raw = raw[len(chunk):]
    return folded


def _rrule(value: str) -> str:
    """Защитно срезать `RRULE:`-префикс из старых записей БД."""
    rule = value.strip()
    while rule.upper().startswith("RRULE:"):
        rule = rule[len("RRULE:"):].strip()
    return rule


def _vevent(event, stamp: str) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.id}@atlas",
        f"DTSTAMP:{stamp}",
    ]
    if event.all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_date_stamp(event.start_at)}")
        # В API `end_at` для all_day — включительный последний день; DTEND по
        # RFC 5545 exclusive, поэтому пишем date(end_at) + 1 день (или start+1).
        last_day = event.end_at if event.end_at is not None else event.start_at
        lines.append(
            f"DTEND;VALUE=DATE:{_date_stamp(last_day + timedelta(days=1))}"
        )
    else:
        lines.append(f"DTSTART:{_utc_stamp(event.start_at)}")
        if event.end_at is not None:
            lines.append(f"DTEND:{_utc_stamp(event.end_at)}")
    lines.append(f"SUMMARY:{_escape(event.title or '')}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    if event.rrule:
        rule = _rrule(event.rrule)
        if rule:
            lines.append(f"RRULE:{rule}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(events) -> str:
    """Собрать VCALENDAR с одним VEVENT на событие; строки — CRLF."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Atlas//RU",
        "CALSCALE:GREGORIAN",
    ]
    for event in events:
        lines.extend(_vevent(event, stamp))
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
