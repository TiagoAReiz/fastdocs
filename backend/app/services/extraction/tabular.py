"""Shared row-group chunking helper for csv/xlsx extractors."""

import pandas as pd

from app.core.config import settings
from app.services.extraction.base import Section


def dataframe_to_sections(df: pd.DataFrame, sheet_name: str) -> list[Section]:
    if df.empty:
        return []
    df = df.fillna("")
    rows_per = settings.TABULAR_ROWS_PER_CHUNK
    header_line = "|".join(str(c) for c in df.columns)
    sections: list[Section] = []
    total = len(df)
    for start in range(0, total, rows_per):
        end = min(start + rows_per, total)
        slice_df = df.iloc[start:end]
        body = slice_df.to_csv(sep="|", index=False, header=False).strip()
        text = f"{header_line}\n{body}"
        sections.append(
            Section(
                text=text,
                metadata={
                    "sheet_name": sheet_name,
                    "row_range": [start + 1, end],  # 1-based inclusive
                    "row_count": end - start,
                },
                kind="tabular",
            )
        )
    return sections
