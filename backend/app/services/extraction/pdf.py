import io

import fitz  # pymupdf
import pytesseract
from pdf2image import convert_from_bytes

from app.core.config import settings
from app.services.extraction.base import ExtractionResult, Section


def extract(content: bytes) -> ExtractionResult:
    doc = fitz.open(stream=content, filetype="pdf")
    page_count = doc.page_count

    native_pages: list[str] = []
    sample_chars = 0
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        native_pages.append(text)
        if i < 3:
            sample_chars += len(text.strip())
    doc.close()

    if sample_chars >= settings.SCANNED_PDF_CHAR_THRESHOLD:
        sections = [
            Section(text=t, metadata={"page_number": i + 1}, kind="text")
            for i, t in enumerate(native_pages)
            if t.strip()
        ]
        return ExtractionResult(
            sections=sections,
            extraction_method="native",
            document_metadata={"page_count": page_count},
        )

    # Scanned PDF — OCR every page via pdf2image + tesseract.
    images = convert_from_bytes(content, dpi=settings.OCR_DPI)
    sections: list[Section] = []
    for i, img in enumerate(images):
        text = pytesseract.image_to_string(img, lang=settings.OCR_LANG)
        if text.strip():
            sections.append(
                Section(text=text, metadata={"page_number": i + 1}, kind="text")
            )
    return ExtractionResult(
        sections=sections,
        extraction_method="tesseract",
        document_metadata={"page_count": page_count},
    )
