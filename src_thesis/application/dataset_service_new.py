"""Facade for dataset inspection, mapping, and source hashing."""

from typing import Any


class DatasetService:
    """Inspect datasets and produce validated dataset references."""

    def inspect(self, dataset_ref: Any) -> Any:
        raise NotImplementedError

    def hash_source(self, dataset_ref: Any) -> str:
        raise NotImplementedError
