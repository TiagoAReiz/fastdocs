from app.services.document_service import _extract_type


def test_extract_type_pdf():
    assert _extract_type("report.pdf") == "pdf"


def test_extract_type_uppercase():
    assert _extract_type("FILE.DOCX") == "docx"


def test_extract_type_no_extension():
    assert _extract_type("noext") == "bin"


def test_extract_type_dotfile():
    # PurePosixPath(".gitignore").suffix is empty, so falls back to "bin"
    assert _extract_type(".gitignore") == "bin"


def test_extract_type_multiple_dots():
    assert _extract_type("archive.tar.gz") == "gz"


def test_extract_type_txt():
    assert _extract_type("notes.txt") == "txt"
