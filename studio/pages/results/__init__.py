"""The Results page: ``page.py`` (the run table, the live view and the tab bar) and
one file per tab: ``learning.py``, ``validation.py``, ``market.py``, ``grid.py``
and ``explore.py``; ``common.py`` holds what they share."""

from studio.pages.results.page import page

__all__ = ["page"]
