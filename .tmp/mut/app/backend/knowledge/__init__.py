"""Knowledge core Atlas: извлечение, чанкинг, triage, сущности, аннотация.

Чистый слой без БД: `pipeline.analyze_file` / `pipeline.should_defer` — единая
точка входа для API и воркера. Логика перенесена из прототипов `scripts/**`.
"""
