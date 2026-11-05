"""The shared report writers.

SmSt Africa carries no PDF or spreadsheet library, so both are written by hand
here and every app builds on them. The apps keep their own `reports/builder.py`
for their own rows; the writing itself lives in this package.
"""

from .pdf import Document, as_count, as_text, fit_text, text_width
from .xlsx import (
    STYLE_BOLD,
    STYLE_DATE,
    STYLE_DEFAULT,
    STYLE_HEADER,
    STYLE_NUMBER,
    STYLE_TOTAL,
    STYLE_TOTAL_NUMBER,
    Sheet,
    Workbook,
)

__all__ = [
    "Document",
    "Sheet",
    "Workbook",
    "as_count",
    "as_text",
    "fit_text",
    "text_width",
    "STYLE_BOLD",
    "STYLE_DATE",
    "STYLE_DEFAULT",
    "STYLE_HEADER",
    "STYLE_NUMBER",
    "STYLE_TOTAL",
    "STYLE_TOTAL_NUMBER",
]
