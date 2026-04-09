from app.services.extraction.base import ExtractionResult, Section


def extract(content: bytes) -> ExtractionResult:
    text = content.decode("utf-8", errors="replace")
    sections = [Section(text=text, metadata={}, kind="markdown")] if text.strip() else []
    return ExtractionResult(
        sections=sections,
        extraction_method="native",
        document_metadata={"char_count": len(text)},
    )
