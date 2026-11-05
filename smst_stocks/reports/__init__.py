"""Report builders for SmSt Stocks.

The PDF and the spreadsheet are written by hand in `core.reports`, so the app
carries no reporting library.
"""

from .builder import build_report, collect

__all__ = ["build_report", "collect"]
