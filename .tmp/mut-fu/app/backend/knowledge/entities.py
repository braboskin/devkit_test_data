"""Сущности правилами v1 (без LLM): люди, организации, места, даты, теги.

Эвристики детерминированные и намеренно грубые: задача — стабильные
кандидаты для карточки документа, а не NER. Уточняется в M3.
"""
from __future__ import annotations

import re
from collections import Counter

HASHTAG_RE = re.compile(r"(?<![\w/])#([A-Za-zА-Яа-яЁё0-9_][\w-]{1,40})")
NAME_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]{1,19})\s+([А-ЯЁ][а-яё]{1,19})"
    r"(?:\s+([А-ЯЁ][а-яё]{1,19}))?\b"
)
ORG_RE = re.compile(
    r"\b(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|НКО|НПО|ФГУП|ГУП|ГБУ|МБУ"
    r"|LLC|Ltd\.?|Inc\.?|GmbH|Corp\.?)"
    r"\s*(?:«[^»]{1,60}»|\"[^\"]{1,60}\"|[А-ЯЁA-Z0-9][\w\-]*"
    r"(?:\s+[А-ЯЁA-Z][\w\-]*){0,3})"
)
PLACE_RE = re.compile(
    r"\b(?:г\.|гор\.|город|с\.|село|пос\.|пгт\.?|дер\.|ст\.)"
    r"\s*([А-ЯЁ][а-яё\-]+(?:\s+[А-ЯЁ][а-яё\-]+)?)"
)
MONTHS = {
    "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "октября", "ноября", "декабря",
}
DATE_RES = (
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:" + "|".join(MONTHS) + r")(?:\s+\d{4})?\b",
        re.IGNORECASE,
    ),
)
WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z][\w-]{3,}")
STOP_WORDS = {
    "сегодня", "вчера", "завтра", "также", "однако", "например", "если",
    "когда", "после", "перед", "кроме", "сейчас", "здесь", "тогда", "потом",
    "важно", "итого", "здравствуйте", "спасибо", "этот", "этом", "этого",
    "который", "которая", "которые", "чтобы", "будет", "было", "были",
    "можно", "нужно", "проект", "проекта", "отчёт", "отчет", "данные",
    "также", "уже", "ещё", "еще", "очень", "всего", "через", "между",
}
NAME_STOP_WORDS = STOP_WORDS | MONTHS | {
    "добрый", "уважаемый", "компания", "организация", "встреча", "итоги",
    "задача", "задачи", "план", "плана", "документ", "документа",
}
MAX_TAGS = 10
FREQ_TAGS = 5
FREQ_MIN_COUNT = 2


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item.strip())
    return result


def extract_people(text: str) -> list[str]:
    people: list[str] = []
    for match in NAME_RE.finditer(text):
        words = [word for word in match.groups() if word]
        if any(word.casefold() in NAME_STOP_WORDS for word in words):
            continue
        if len(words) == 3 and words[2].casefold() in MONTHS:
            words = words[:2]
        people.append(" ".join(words))
    return _dedupe(people)


def extract_orgs(text: str) -> list[str]:
    return _dedupe([match.group(0).strip() for match in ORG_RE.finditer(text)])


def extract_places(text: str) -> list[str]:
    places: list[str] = []
    for match in PLACE_RE.finditer(text):
        name = match.group(1)
        if name.split()[0].casefold() in MONTHS:
            continue
        places.append(match.group(0).strip(" .,;"))
    return _dedupe(places)


def extract_dates(text: str) -> list[str]:
    dates: list[str] = []
    for pattern in DATE_RES:
        dates.extend(match.group(0) for match in pattern.finditer(text))
    return _dedupe(dates)


def extract_tags(text: str, frontmatter: dict | None = None) -> list[str]:
    tags: list[str] = []
    raw = (frontmatter or {}).get("tags") or []
    if isinstance(raw, str):
        raw = [raw]
    for tag in raw:
        tags.append(str(tag).lower().lstrip("#").strip())
    tags.extend(match.group(1).lower() for match in HASHTAG_RE.finditer(text))
    words = Counter(
        word.lower()
        for word in WORD_RE.findall(text)
        if word.lower() not in STOP_WORDS
    )
    for word, count in words.most_common(FREQ_TAGS):
        if count >= FREQ_MIN_COUNT:
            tags.append(word)
    return _dedupe([tag for tag in tags if tag])[:MAX_TAGS]


def extract_entities(text: str, frontmatter: dict | None = None) -> dict:
    text = text or ""
    return {
        "people": extract_people(text),
        "orgs": extract_orgs(text),
        "places": extract_places(text),
        "dates": extract_dates(text),
        "tags": extract_tags(text, frontmatter=frontmatter),
    }
