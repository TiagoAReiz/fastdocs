import io

import pandas as pd

from app.services.extraction.base import ExtractionResult
from app.services.extraction.tabular import dataframe_to_sections


def extract(content: bytes) -> ExtractionResult:
    df = pd.read_csv(io.BytesIO(content))
    sections = dataframe_to_sections(df, sheet_name="csv")
    return ExtractionResult(
        sections=sections,
        extraction_method="native",
        document_metadata={"row_count": len(df)},
    )
