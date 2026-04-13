import io

import fitz  # pymupdf
import pytesseract
from pdf2image import convert_from_bytes

from app.core.config import settings
from app.services.extraction.base import ExtractionResult, Section

_CONFIDENCE_THRESHOLD = 60
_LOW_CONFIDENCE_ALERT = 50


def _ocr_page(img) -> tuple[str, float]:
    """Run Tesseract on a single page image, filtering low-confidence words.

    Returns (extracted_text, mean_confidence).
    """
    data = pytesseract.image_to_data(
        img, lang=settings.OCR_LANG, output_type=pytesseract.Output.DATAFRAME
    )
    # Filter out non-word rows and low confidence
    words = data[(data["conf"] >= 0) & (data["text"].notna())]
    if words.empty:
        return "", 0.0

    mean_conf = float(words["conf"].mean())
    good_words = words[words["conf"] >= _CONFIDENCE_THRESHOLD]

    lines: dict[int, list[str]] = {}
    for _, row in good_words.iterrows():
        line_num = int(row["line_num"])
        lines.setdefault(line_num, []).append(str(row["text"]))

    text = "\n".join(" ".join(words) for words in lines.values())
    return text, mean_conf


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
    page_confidences: list[float] = []
    notes: list[str] = []

    for i, img in enumerate(images):
        text, mean_conf = _ocr_page(img)
        page_confidences.append(mean_conf)
        if mean_conf < _LOW_CONFIDENCE_ALERT:
            notes.append(f"page {i + 1}: low OCR confidence ({mean_conf:.1f}%)")
        if text.strip():
            sections.append(
                Section(
                    text=text,
                    metadata={"page_number": i + 1, "ocr_confidence": round(mean_conf, 1)},
                    kind="text",
                )
            )

    overall_conf = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0
    extraction_notes = ""
    if overall_conf < _LOW_CONFIDENCE_ALERT:
        extraction_notes = f"Low overall OCR confidence: {overall_conf:.1f}%. " + "; ".join(notes)
    elif notes:
        extraction_notes = "; ".join(notes)

    return ExtractionResult(
        sections=sections,
        extraction_method="tesseract",
        document_metadata={"page_count": page_count, "ocr_confidence": round(overall_conf, 1)},
        extraction_notes=extraction_notes,
    )
