"""TariffService: the DSO tariff CSVs an experiment uses (04 §5)."""

from __future__ import annotations

from src_thesis.platform.services.data_files import data_files, read_csv
from src_thesis.platform.services.models import ExperimentFile, Series
from src_thesis.platform.experiments.models.manifest import data_path
from src_thesis.platform.experiments.models.sections import ProfileRef, Tariffs

TARIFF_FOLDER = "data/prices"
# The CSVs the original MARLEM notebooks use when the file names none.
TARIFF_DEFAULTS = {
    "feed_in": "data/prices/fit_60min.csv",
    "utility": "data/prices/utility_60min.csv",
}


class TariffService:
    """Feed-in tariffs and utility prices of the DSO (Market & DSO page)."""

    SAMPLE_DATA = False

    def tariff_files(self) -> dict[str, list[str]]:
        """The DSO tariff CSVs (``data/prices``); each column is one daily profile."""
        return data_files(TARIFF_FOLDER)

    def tariffs(self, file: ExperimentFile) -> Series:
        """The DSO tariff profiles the file selects, as stored in the CSVs.

        Built: for ``dso.tariffs.source = "csv"``, the feed-in and utility CSVs
        (or the original defaults) over one day; one line per column, or only the
        chosen column. These are the raw values: the DSO maps them into the
        market's price bounds when the environment runs. ``synthetic`` tariffs are
        generated per episode, so there is no fixed curve (empty series).
        """
        tariffs = file.dso.tariffs or Tariffs()
        if (tariffs.source or "synthetic") != "csv":
            return Series(x=[], y={}, x_label="time of day", y_label="price")
        x: list[str] = []
        y: dict[str, list[float]] = {}
        for key, label in (("feed_in", "feed-in"), ("utility", "utility")):
            spec = getattr(tariffs, key) or ProfileRef(path=TARIFF_DEFAULTS[key])
            if not spec.path:
                raise ValueError(f"dso.tariffs.{key} names no CSV file (path)")
            columns = read_csv(data_path(spec.path))
            chosen = [spec.column] if spec.column else list(columns)
            for column in chosen:
                if column not in columns:
                    raise ValueError(f"{spec.path} has no column {column!r}")
                values = columns[column]
                y[f"{label} · {column}"] = values
                x = x if len(x) >= len(values) else _times_of_day(len(values))
        return Series(x=x, y=y, x_label="time of day", y_label="price")


def _times_of_day(rows: int) -> list[str]:
    """``HH:MM`` labels for ``rows`` equal steps over one day."""
    minutes = 24 * 60 // max(rows, 1)
    return [f"{i * minutes // 60:02d}:{i * minutes % 60:02d}" for i in range(rows)]
