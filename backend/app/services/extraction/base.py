from dataclasses import dataclass, field
from typing import Any, Literal

SectionKind = Literal["text", "tabular", "markdown"]


@dataclass
class Section:
    """A logical region of a document carrying metadata used for chunking + retrieval."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: SectionKind = "text"


@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0


@dataclass
class ExtractionResult:
    sections: list[Section]
    extraction_method: str = "native"  # "native" | "tesseract"
    document_metadata: dict[str, Any] = field(default_factory=dict)
    extraction_notes: str = ""
