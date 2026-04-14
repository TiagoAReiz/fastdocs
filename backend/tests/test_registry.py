import pytest

from app.services.extraction.base import ExtractionResult
from app.services.extraction.registry import EXTRACTORS, UnsupportedFormatError, extract


def test_extract_routes_to_txt():
    result = extract("txt", b"hello world")
    assert isinstance(result, ExtractionResult)
    assert len(result.sections) == 1
    assert "hello world" in result.sections[0].text


def test_extract_case_insensitive():
    result = extract("TXT", b"case test")
    assert isinstance(result, ExtractionResult)
    assert len(result.sections) >= 1


def test_unsupported_format_raises():
    with pytest.raises(UnsupportedFormatError, match="xyz"):
        extract("xyz", b"")


def test_all_registered_types_are_callable():
    for file_type, extractor_fn in EXTRACTORS.items():
        assert callable(extractor_fn), f"Extractor for {file_type} is not callable"
