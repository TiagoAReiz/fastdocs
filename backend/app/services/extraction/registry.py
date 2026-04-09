from collections.abc import Callable

from app.services.extraction import csv, docx, image, md, pdf, pptx, txt, xlsx
from app.services.extraction.base import ExtractionResult

Extractor = Callable[[bytes], ExtractionResult]

EXTRACTORS: dict[str, Extractor] = {
    "pdf": pdf.extract,
    "docx": docx.extract,
    "xlsx": xlsx.extract,
    "xls": xlsx.extract,
    "csv": csv.extract,
    "txt": txt.extract,
    "md": md.extract,
    "markdown": md.extract,
    "pptx": pptx.extract,
    "png": image.extract,
    "jpg": image.extract,
    "jpeg": image.extract,
}


class UnsupportedFormatError(Exception):
    pass


def extract(file_type: str, content: bytes) -> ExtractionResult:
    extractor = EXTRACTORS.get(file_type.lower())
    if extractor is None:
        raise UnsupportedFormatError(f"Unsupported file type: {file_type}")
    return extractor(content)
