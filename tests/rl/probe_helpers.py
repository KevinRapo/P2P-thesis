"""Shared helpers for the probe tests: actions to send, and readable printing."""

import numpy as np


def same_action(env, value):
    """The same action ``value`` for every agent."""
    return {agent: np.array([value], dtype=np.float32) for agent in env.agents_id}


def per_agent(values):
    """Per-agent values on one line, e.g. ``agent_2=1.0  agent_10=0.0``."""
    return "  ".join(
        f"{agent}={np.round(np.asarray(value).squeeze(), 3)}"
        for agent, value in values.items()
        if agent != "__all__"
    )
