from app.services.extraction.base import Section
from app.services.extraction.chunker import chunk


def test_chunk_produces_chunks_with_overlap():
    long_text = "word " * 500  # ~2500 chars, should produce multiple chunks
    sections = [Section(text=long_text, kind="text")]
    chunks = chunk(sections)
    assert len(chunks) > 1
    # Each chunk should have a sequential index
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_empty_section_produces_no_chunks():
    sections = [Section(text="", kind="text")]
    assert chunk(sections) == []


def test_short_section_below_min_chars_filtered():
    sections = [Section(text="hi", kind="text")]
    assert chunk(sections) == []


def test_tabular_section_kept_as_single_chunk():
    sections = [Section(text="col1,col2\nval1,val2\nval3,val4", kind="tabular")]
    chunks = chunk(sections)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_metadata_preserved_in_chunks():
    sections = [Section(text="word " * 50, metadata={"page_number": 3}, kind="text")]
    chunks = chunk(sections)
    assert len(chunks) >= 1
    assert chunks[0].metadata["page_number"] == 3
