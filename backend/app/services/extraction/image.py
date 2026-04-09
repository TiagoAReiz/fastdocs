import io

import pytesseract
from PIL import Image

from app.core.config import settings
from app.services.extraction.base import ExtractionResult, Section


def extract(content: bytes) -> ExtractionResult:
    img = Image.open(io.BytesIO(content))
    text = pytesseract.image_to_string(img, lang=settings.OCR_LANG)
    sections = [Section(text=text, metadata={}, kind="text")] if text.strip() else []
    return ExtractionResult(
        sections=sections,
        extraction_method="tesseract",
        document_metadata={"width": img.width, "height": img.height},
    )
