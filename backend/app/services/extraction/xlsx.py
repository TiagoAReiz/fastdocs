import io

import pandas as pd

from app.services.extraction.base import ExtractionResult
from app.services.extraction.tabular import dataframe_to_sections


def extract(content: bytes) -> ExtractionResult:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine="openpyxl")
    sections = []
    for name, df in sheets.items():
        sections.extend(dataframe_to_sections(df, sheet_name=str(name)))
    return ExtractionResult(
        sections=sections,
        extraction_method="native",
        document_metadata={"sheet_count": len(sheets)},
    )
