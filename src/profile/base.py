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

    def _load_profile(self,
                      path: Path,
                      value_column: Optional[str] = None,
                      steps: Optional[int] = None,
                      timestamp_column: Optional[str] = None,
                      replay_start: Optional[str] = None,
                      replay_end: Optional[str] = None,
                      expected_frequency: Optional[str] = None) -> List[float]:
        """Load one deterministic numeric profile column for measured replay.

        Args:
            path: Path to the CSV file

        Returns:
            Profile list
        """
        df = pd.read_csv(path)
        if timestamp_column is not None:
            if timestamp_column not in df.columns:
                raise ValueError(f"Timestamp column '{timestamp_column}' is not present in {path}.")
            timestamps = pd.to_datetime(df[timestamp_column], errors="raise")
            if timestamps.isna().any() or not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
                raise ValueError(f"Timestamp column '{timestamp_column}' must be unique and increasing.")
            if len(timestamps) > 1:
                deltas = timestamps.diff().iloc[1:]
                target = pd.Timedelta(expected_frequency) if expected_frequency else deltas.iloc[0]
                if not (deltas == target).all():
                    raise ValueError(f"Timestamp column '{timestamp_column}' does not have the expected regular frequency.")
            if replay_start is not None:
                df = df.loc[timestamps >= pd.Timestamp(replay_start)]
                timestamps = timestamps.loc[df.index]
            if replay_end is not None:
                df = df.loc[timestamps <= pd.Timestamp(replay_end)]
        selected_col = value_column or df.columns[0]
        if selected_col not in df.columns:
            raise ValueError(f"Profile column '{selected_col}' is not present in {path}.")
        values = pd.to_numeric(df[selected_col], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Profile column '{selected_col}' contains non-finite values.")
        if steps is not None and len(values) < steps:
            raise ValueError(f"Profile column '{selected_col}' has {len(values)} values; {steps} are required.")
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
