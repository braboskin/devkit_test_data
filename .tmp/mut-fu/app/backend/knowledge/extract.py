"""Извлечение текста: PDF (PyMuPDF + OCR), изображения, Markdown, DOCX.

PDF: PyMuPDF. Если страница почти без текста — рендер в PNG и OCR Tesseract.
Изображения: Tesseract (rus+eng) через stdout, без временных файлов
pytesseract. DOCX: python-docx — параграфы и таблицы, без картинок.

Docling не подключён: тяжёлые зависимости. Адаптер можно добавить отдельной
задачей; контракт `extract_pdf` при этом сохранится.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
TESSERACT = ROOT / ".tools" / "tesseract" / "tesseract.exe"
TESSDATA = ROOT / ".tools" / "tesseract" / "tessdata"
TMP_DIR = ROOT / ".tmp" / "tesseract"
MIN_TEXT = 10
OCR_DPI = 200
LANG = "rus+eng"

MD_EXT = {".md", ".markdown"}
PDF_EXT = {".pdf"}
DOCX_EXT = {".docx"}
TXT_EXT = {".txt"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
SUPPORTED = MD_EXT | PDF_EXT | DOCX_EXT | TXT_EXT | IMAGE_EXT

FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.S)


def tesseract_binary() -> str:
    if TESSERACT.exists():
        return str(TESSERACT)
    found = shutil.which("tesseract")
    if found:
        return found
    raise FileNotFoundError(
        "tesseract не найден: положите его в .tools/tesseract или добавьте в PATH"
    )


def tesseract_env() -> dict:
    env = os.environ.copy()
    if TESSDATA.exists():
        env["TESSDATA_PREFIX"] = str(TESSDATA)
    return env


def run_tesseract(image_path: Path, lang: str = LANG) -> str:
    binary = tesseract_binary()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for language in (lang, "eng"):
        proc = subprocess.run(
            [binary, str(image_path), "stdout", "-l", language],
            capture_output=True,
            env=tesseract_env(),
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace").strip()
    return ""


def ocr_image(image: Image.Image, lang: str = LANG) -> str:
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TMP_DIR / f"ocr-{uuid.uuid4().hex}.png"
    image.save(tmp)
    try:
        return run_tesseract(tmp, lang=lang)
    finally:
        tmp.unlink(missing_ok=True)


def extract_pdf(path: Path, ocr: bool = True) -> dict:
    document = pymupdf.open(path)
    metadata = document.metadata or {}
    pages: list[str] = []
    ocr_pages = 0

    for page in document:
        text = page.get_text("text").strip()
        if ocr and len(text) < 40:
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            tmp = TMP_DIR / f"page-{uuid.uuid4().hex}.png"
            pixmap = page.get_pixmap(dpi=OCR_DPI)
            pixmap.save(tmp)
            try:
                ocr_text = run_tesseract(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            if ocr_text:
                text = f"{text}\n{ocr_text}".strip() if text else ocr_text
                ocr_pages += 1
        pages.append(text)

    page_count = len(pages)
    document.close()
    full = "\n\n".join(part for part in pages if part).strip()
    quality = "ok" if len(full) >= MIN_TEXT else "needs_review"
    return {
        "text": full,
        "pages": page_count,
        "ocr_pages": ocr_pages,
        "engine": "pymupdf+tesseract" if ocr_pages else "pymupdf",
        "quality": quality,
        "reason": "text extracted" if quality == "ok" else "too little text",
        "title": str(metadata.get("title") or "").strip(),
    }


def extract_image(path: Path, lang: str = LANG) -> dict:
    with Image.open(path) as image:
        width, height = image.size
        text = ocr_image(image, lang=lang)
    quality = "ok" if len(text) >= MIN_TEXT else "needs_review"
    return {
        "text": text,
        "pages": 1,
        "ocr_pages": 1,
        "engine": "tesseract",
        "quality": quality,
        "reason": "ocr text extracted" if quality == "ok" else "too little text",
        "title": "",
        "width": width,
        "height": height,
    }


def extract_docx(path: Path) -> dict:
    from docx import Document

    document = Document(str(path))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            line = " | ".join(cell for cell in cells if cell)
            if line:
                parts.append(line)
    props = document.core_properties
    title = str(getattr(props, "title", "") or "").strip()
    full = "\n\n".join(parts).strip()
    quality = "ok" if len(full) >= MIN_TEXT else "needs_review"
    return {
        "text": full,
        "pages": None,
        "ocr_pages": 0,
        "engine": "python-docx",
        "quality": quality,
        "reason": "text extracted" if quality == "ok" else "too little text",
        "title": title,
    }


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_scalar(raw: str):
    s = raw.strip()
    if not s:
        return None
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(x) for x in inner.split(",")]
    return s


def parse_frontmatter(text: str):
    """Минимальный YAML-подобный frontmatter.

    # ponytail: дубль `scripts/frontmatter.py` (этот файл вне scope WS-B);
    # схлопнуть в knowledge-модуль, когда `scripts/**` перестанут использоваться.
    """
    m = FM_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\s+-\s+", line):
            if current is None:
                continue
            item = re.sub(r"^\s+-\s+", "", line).strip()
            if not isinstance(meta.get(current), list):
                meta[current] = []
            meta[current].append(parse_scalar(item))
            continue
        m2 = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if m2:
            key, rest = m2.group(1), m2.group(2)
            current = key
            meta[key] = [] if rest.strip() == "" else parse_scalar(rest)
    return meta, body


def normalize_body(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return f"{text}\n" if text else ""


def extract_markdown(path: Path) -> dict:
    raw = read_text(path)
    meta, body = parse_frontmatter(raw)
    return {
        "text": body,
        "meta": meta,
        "format": "md",
        "pages": None,
        "ocr_pages": 0,
        "engine": "markdown",
        "quality": "ok",
        "reason": "text extracted",
        "title": str(meta.get("title") or ""),
    }


def extract_text_file(path: Path) -> dict:
    body = read_text(path)
    quality = "ok" if len(body.strip()) >= MIN_TEXT else "needs_review"
    return {
        "text": body,
        "meta": {},
        "format": "txt",
        "pages": None,
        "ocr_pages": 0,
        "engine": "plain",
        "quality": quality,
        "reason": "text extracted" if quality == "ok" else "too little text",
        "title": "",
    }


def extract_file(path: Path, suffix: str | None = None) -> dict:
    suffix = (suffix or path.suffix).lower()
    if suffix in MD_EXT:
        return extract_markdown(path)
    if suffix in TXT_EXT:
        return extract_text_file(path)
    if suffix in PDF_EXT:
        data = extract_pdf(path)
        data["format"] = "pdf"
    elif suffix in IMAGE_EXT:
        data = extract_image(path)
        data["format"] = suffix.lstrip(".")
    elif suffix in DOCX_EXT:
        data = extract_docx(path)
        data["format"] = "docx"
    else:
        raise ValueError(f"unsupported format: {suffix}")
    data.setdefault("meta", {})
    return data
