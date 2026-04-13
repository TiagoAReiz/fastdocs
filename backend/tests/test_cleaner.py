from app.services.extraction.base import Section
from app.services.extraction.cleaner import clean_sections


def test_removes_excessive_newlines():
    sections = [Section(text="Hello\n\n\n\n\nWorld. " * 5, kind="text")]
    result = clean_sections(sections)
    assert len(result) == 1
    assert "\n\n\n" not in result[0].text


def test_filters_short_sections():
    sections = [
        Section(text="too short", kind="text"),
        Section(text="This is a longer section with enough content to pass the filter easily.", kind="text"),
    ]
    result = clean_sections(sections)
    assert len(result) == 1
    assert "longer section" in result[0].text


def test_removes_null_bytes():
    sections = [Section(text="Hello\x00World. " * 10, kind="text")]
    result = clean_sections(sections)
    assert len(result) == 1
    assert "\x00" not in result[0].text


def test_preserves_metadata_and_kind():
    sections = [Section(text="A" * 100, metadata={"page": 1}, kind="tabular")]
    result = clean_sections(sections)
    assert result[0].metadata == {"page": 1}
    assert result[0].kind == "tabular"
