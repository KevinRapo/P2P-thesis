"""Numeric guards for values handed to RL (clipping to safe ranges)."""

from enum import Enum


class RLProtection(Enum):
    """Supported RL protection methods."""

    MAX_SAFE_VALUE = 1e5

    @staticmethod
    def clip_value(
        value: float,
        min_value: float = -MAX_SAFE_VALUE,
        max_value: float = MAX_SAFE_VALUE,
    ) -> float:
        """Clip a value to the maximum safe value.

        Args:
            value: The value to clip.
            min_value: Minimum value for clipping (defaults to -1e5).
            max_value: Maximum value for clipping (defaults to 1e5).

        Returns:
            The clipped value.
        """
        return max(min_value, min(max_value, value))
