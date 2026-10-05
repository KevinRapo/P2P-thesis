"""CSV files in the repository's ``data/`` folder: listing and reading them.

The original MARLEM data (demand, generation, DSO tariffs) are CSVs with one
profile per column; paths are stored repository-relative in experiment files.
"""

from __future__ import annotations

import csv
from typing import Any

from src_thesis.experiments.models.manifest import REPO


def data_files(folder: str) -> dict[str, list[str]]:
    """The CSVs in a data folder of the repository, with their columns.

    Built: e.g. ``data/demand``, ``data/generation`` or ``data/prices``; each
    column is one profile. Paths are repository-relative, as the file stores
    them.

    Raises:
        ValueError: ``folder`` is not inside the repository's ``data``.
    """
    root = (REPO / "data").resolve()
    path = (REPO / folder).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"{folder!r} is not a data folder")
    return {
        f"{folder.rstrip('/')}/{csv_path.name}": csv_columns(csv_path)
        for csv_path in sorted(path.glob("*.csv"))
    }


def read_csv(path: Any) -> dict[str, list[float]]:
    """Column -> values of a numeric CSV; empty cells (shorter columns) are left
    out.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}
    return {c: [float(r[c]) for r in rows if (r[c] or "").strip()] for c in rows[0]}


def csv_columns(path: Any) -> list[str]:
    """The header of a CSV."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), [])
