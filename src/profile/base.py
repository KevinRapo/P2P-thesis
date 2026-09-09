"""
Base class for profile management.

This module handles loading, generation, and management of time-varying profiles.
"""

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd


class ProfileHandler:
    """Base class for profile management with common functionality."""

    def __init__(self,
                 seed: Optional[int] = None,
                 decimals: int = 1) -> None:
        """Initialize the base profile handler.

        Args:
            seed: Random seed for reproducibility
            decimals: Number of decimal places for rounding (default: 1)
        """
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.decimals = decimals

    def _load_profile(self, path: Path, value_column: Optional[str] = None,
                      steps: Optional[int] = None) -> List[float]:
        """Read one numeric CSV profile and validate the requested episode length."""
        df = pd.read_csv(path)
        column = value_column or df.columns[0]
        if column not in df.columns:
            raise ValueError(f"Profile column {column!r} is absent from {path}.")
        values = pd.to_numeric(df[column], errors='raise').to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Profile {column!r} contains non-finite values.")
        if steps is not None and len(values) < steps:
            raise ValueError(f"Profile has {len(values)} values; {steps} are required.")
        return values[:steps].tolist() if steps is not None else values.tolist()

    def _apply_smoothing(self,
                         profile: List[float],
                         window_size: int = 3) -> List[float]:
        """Applies a simple moving average filter to smooth a profile.

        Args:
            profile: The profile data to smooth.
            window_size: The size of the moving average window.

        Returns:
            The smoothed profile.
        """
        if (window_size <= 1) or (len(profile) < window_size):
            return profile

        kernel = np.ones(window_size) / window_size
        smoothed_arr = np.convolve(profile, kernel, mode='same')

        return [round(float(x), self.decimals) for x in smoothed_arr]
