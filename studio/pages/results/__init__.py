"""The Results page: ``page.py`` (the run table, the live view and the tab bar) and
one file per tab: ``validation.py``, ``learning.py``, ``market.py`` and ``grid.py``;
``common.py`` and ``steps.py`` hold what they share."""

from studio.pages.results.page import page

__all__ = ["page"]
