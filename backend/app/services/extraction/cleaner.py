import re

from app.services.extraction.base import Section

_MIN_USEFUL_CHARS = 50


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _try_decode(raw: bytes) -> str:
    """Best-effort decode bytes to str, handling latin-1 common in Brazilian PDFs."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


def clean_sections(sections: list[Section]) -> list[Section]:
    cleaned: list[Section] = []
    for section in sections:
        text = _normalize_text(section.text)
        if len(text) < _MIN_USEFUL_CHARS:
            continue
        cleaned.append(
            Section(text=text, metadata=section.metadata, kind=section.kind)
        )
    return cleaned
