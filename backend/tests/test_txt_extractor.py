from app.services.extraction.txt import extract


def test_utf8_text():
    result = extract(b"Hello World")
    assert len(result.sections) == 1
    assert result.sections[0].text == "Hello World"
    assert result.extraction_method == "native"


def test_empty_content():
    result = extract(b"")
    assert result.sections == []
    assert result.extraction_method == "native"


def test_whitespace_only_content():
    result = extract(b"   \n\t  ")
    assert result.sections == []


def test_metadata_has_char_count():
    result = extract(b"some text")
    assert "char_count" in result.document_metadata
    assert result.document_metadata["char_count"] == len("some text")
