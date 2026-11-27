import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\app\backend\features\agent\schemas.py")
s = p.read_text(encoding="utf-8")

old = """class ProfileIn(BaseModel):
    data: dict[str, Any]
    summary: Summary | None = None
"""
new = '''class ProfileIn(BaseModel):
    data: dict[str, Any]
    summary: Summary | None = None

    @field_validator("data")
    @classmethod
    def _validate_person(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Типизированные поля профиля поверх свободного JSON (без миграции БД).

        Известные ключи проверяются (имя/город/деятельность ≤ 120, возраст
        14–120), произвольные ключи сохраняются как есть — старые профили с
        ручными данными продолжают работать.
        """
        person = {
            "name": PERSON_FIELD,
            "city": PERSON_FIELD,
            "occupation": PERSON_FIELD,
        }
        for key, limit in person.items():
            raw = value.get(key)
            if raw is None:
                continue
            if not isinstance(raw, str):
                raise ValueError(f"{key} must be a string")
            text = raw.strip()
            if len(text) > limit:
                raise ValueError(f"{key} is too long")
            if text:
                value[key] = text
            else:
                value.pop(key, None)
        age = value.get("age")
        if age is not None:
            if isinstance(age, bool) or not isinstance(age, int):
                raise ValueError("age must be an integer")
            if not 14 <= age <= 120:
                raise ValueError("age must be between 14 and 120")
        return value
'''
assert old in s, "ProfileIn pattern not found"
s = s.replace(old, new, 1)
s = s.replace(
    "from pydantic import BaseModel, ConfigDict, Field, StringConstraints",
    "from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator",
    1,
)
s = s.replace(
    "Summary = Annotated[str, StringConstraints(max_length=4000)]",
    "Summary = Annotated[str, StringConstraints(max_length=4000)]\nPERSON_FIELD = 120",
    1,
)
p.write_text(s, encoding="utf-8")
print("ProfileIn validator added")
