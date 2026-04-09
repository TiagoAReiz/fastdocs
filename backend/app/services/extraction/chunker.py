import re

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.core.config import settings
from app.services.extraction.base import Chunk, Section

_MIN_CHUNK_CHARS = 10

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " "],
)

_md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
)


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _split_text(section: Section) -> list[tuple[str, dict]]:
    cleaned = _clean(section.text)
    if not cleaned:
        return []
    pieces = _text_splitter.split_text(cleaned)
    return [(p, dict(section.metadata)) for p in pieces]


def _split_markdown(section: Section) -> list[tuple[str, dict]]:
    cleaned = _clean(section.text)
    if not cleaned:
        return []
    md_docs = _md_splitter.split_text(cleaned)
    out: list[tuple[str, dict]] = []
    for doc in md_docs:
        meta = dict(section.metadata)
        meta.update(doc.metadata or {})
        # MD sections may still be huge — re-split.
        for piece in _text_splitter.split_text(doc.page_content):
            out.append((piece, dict(meta)))
    return out


def chunk(sections: list[Section]) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for section in sections:
        if section.kind == "tabular":
            cleaned = _clean(section.text)
            if cleaned:
                chunks.append(
                    Chunk(text=cleaned, metadata=dict(section.metadata), chunk_index=idx)
                )
                idx += 1
            continue

        if section.kind == "markdown":
            pieces = _split_markdown(section)
        else:
            pieces = _split_text(section)

        for text, meta in pieces:
            if len(text) < _MIN_CHUNK_CHARS:
                continue
            chunks.append(Chunk(text=text, metadata=meta, chunk_index=idx))
            idx += 1
    return chunks
