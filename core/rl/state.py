"""The global state: every agent's observation joined into one vector.

``s = [o_1, ..., o_N]`` in the environment's agent order (``env.agents_id``). It is
what the CTCE controller observes (``core/rl/ctce.py``) and what the CTDE critic
reads next to the agent's own observation (``core/rl/ctde.py``).

Fixes L-05: the original put the agents' spaces in sorted name order and their
data in environment order. Here both follow ``env.agents_id``.
"""

from __future__ import annotations

import numpy as np
from gymnasium import spaces


def join_spaces(boxes: list[spaces.Box]) -> spaces.Box:
    """One ``Box`` holding the given boxes one after the other."""
    return spaces.Box(
        low=np.concatenate([b.low.reshape(-1) for b in boxes]),
        high=np.concatenate([b.high.reshape(-1) for b in boxes]),
        dtype=np.float32,
    )


def join(values: dict, agents: list[str]) -> np.ndarray:
    """Join each agent's vector into one, in ``agents`` order."""
    return np.concatenate(
        [np.asarray(values[a], dtype=np.float32).reshape(-1) for a in agents]
    )
