"""The one place SmSt Stocks reaches into SmSt Finances.

The two apps share one book, and SmSt Finances imports the stock models at
module level, so the stock app cannot import finances that way without closing
a cycle. Every finance import here is deferred until it is first used, which
keeps the direction open and lets the stock app run on a deployment where
finances is not installed.

Nothing is swallowed here: a missing app still raises ImportError, and the
caller decides what that means for its own request.
"""

from __future__ import annotations


def services():
    """The SmSt Finances rules: syncing a movement, posting an entry."""
    from smst_finances import services as module

    return module


def models():
    """The SmSt Finances models: the chart of accounts and the options."""
    from smst_finances import models as module

    return module


def receipts():
    """The SmSt Finances receipt writer: the PDF a processed cart line leaves."""
    from smst_finances import receipts as module

    return module
