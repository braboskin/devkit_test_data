"""Генерация фикстур T-103: 5 PDF с текстом и 5 PNG для OCR."""
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "docs"
OUT.mkdir(parents=True, exist_ok=True)

PDFS = {
    "01-project-brief.pdf": (
        "Atlas project brief\n\n"
        "Phase 1: knowledge core.\n"
        "Qdrant, ingestion, MCP."
    ),
    "02-health-plan.pdf": (
        "Health plan\n\n"
        "Sleep 7-8 hours.\n"
        "Training twice a week."
    ),
    "03-finance-report.pdf": (
        "Finance report\n\n"
        "Budget categories.\n"
        "Reserve 10 percent."
    ),
    "04-learning-notes.pdf": (
        "Learning notes\n\n"
        "Practice over theory.\n"
        "Small projects."
    ),
    "05-meeting-notes.pdf": (
        "Meeting notes\n\n"
        "Decisions and next steps.\n"
        "Owner and deadline."
    ),
}

IMAGES = {
    "01-sleep.png": "Сон восемь часов\nПодъём в семь утра",
    "02-training.png": "Тренировка два раза\nСиловые блоки",
    "03-budget.png": "Бюджет на месяц\nРезерв десять процентов",
    "04-focus.png": "Фокус девяносто минут\nОдна задача",
    "05-metrics.png": "Метрики недели\nСон и тренировки",
}


def make_pdfs() -> None:
    for name, text in PDFS.items():
        document = pymupdf.open()
        page = document.new_page()
        page.insert_textbox(
            pymupdf.Rect(72, 72, 520, 720),
            text,
            fontsize=14,
            fontname="helv",
        )
        document.save(OUT / name)
        document.close()


def make_images() -> None:
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40)
    for name, text in IMAGES.items():
        image = Image.new("RGB", (1100, 500), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text((50, 50), text, fill="black", font=font, spacing=14)
        image.save(OUT / name)


if __name__ == "__main__":
    make_pdfs()
    make_images()
    print(f"generated: {len(PDFS)} pdf, {len(IMAGES)} png in {OUT}")
