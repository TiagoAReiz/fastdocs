from unittest.mock import MagicMock, patch

import fitz
import pandas as pd
import pytest

from app.services.extraction.pdf import extract


def _make_text_pdf(text: str = "Hello World " * 50) -> bytes:
    """Create a minimal PDF with native text using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    content = doc.tobytes()
    doc.close()
    return content


def _make_blank_pdf(pages: int = 1) -> bytes:
    """Create a PDF with blank pages (no text)."""
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    content = doc.tobytes()
    doc.close()
    return content


def test_native_extraction():
    content = _make_text_pdf("This is a test document with enough text to pass the threshold. " * 10)
    result = extract(content)
    assert result.extraction_method == "native"
    assert len(result.sections) >= 1
    assert "test document" in result.sections[0].text
    assert result.sections[0].metadata.get("page_number") == 1
    assert result.document_metadata.get("page_count") == 1


def test_scanned_pdf_triggers_ocr():
    content = _make_blank_pdf(pages=3)

    mock_img = MagicMock()
    mock_df = pd.DataFrame(
        {
            "conf": [90.0, 85.0, 70.0],
            "text": ["hello", "world", "test"],
            "line_num": [1, 1, 2],
        }
    )

    with (
        patch("app.services.extraction.pdf.convert_from_bytes", return_value=[mock_img] * 3),
        patch("app.services.extraction.pdf.pytesseract") as mock_tess,
    ):
        mock_tess.Output.DATAFRAME = "dataframe"
        mock_tess.image_to_data.return_value = mock_df
        result = extract(content)

    assert result.extraction_method == "tesseract"
    assert len(result.sections) >= 1
    assert result.document_metadata.get("page_count") == 3


def test_empty_pdf_native():
    content = _make_blank_pdf(pages=1)

    # With 1 blank page, sample_chars < threshold, so it goes to OCR path.
    # Mock OCR returning empty results.
    mock_img = MagicMock()
    empty_df = pd.DataFrame({"conf": [], "text": [], "line_num": []})

    with (
        patch("app.services.extraction.pdf.convert_from_bytes", return_value=[mock_img]),
        patch("app.services.extraction.pdf.pytesseract") as mock_tess,
    ):
        mock_tess.Output.DATAFRAME = "dataframe"
        mock_tess.image_to_data.return_value = empty_df
        result = extract(content)

    assert result.sections == []
    assert result.extraction_method == "tesseract"
