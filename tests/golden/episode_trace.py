"""Fixed-seed episodes of the local energy market, as plain data.

Why: the code is restructured without changing what it does. These episodes are
recorded once (``episodes.json``) and replayed by ``tests/test_golden_episode.py``;
every observation, reward, flag, info value and the agents' and DSO's state after
each step must stay the same. Only the imports below follow the code when it moves.

    python tests/golden/episode_trace.py   # re-record (only when behaviour may change)
"""

from __future__ import annotations

import dataclasses
import json
import random
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from src_thesis.adapters.grid.network import GridNetwork  # noqa: E402
from src_thesis.core.location import GridTopology  # noqa: E402
from src_thesis.environment.lem import LocalEnergyMarket  # noqa: E402
from src_thesis.marketplace.market.mechanism import ClearingMechanism  # noqa: E402

FILE = Path(__file__).with_name("episodes.json")
DIGITS = 9
# Values that depend on the wall clock or on hashes of them.
VOLATILE = {"timestamp", "hash", "previous_hash", "nonce", "time", "created_at"}


def plain(value: Any, depth: int = 0) -> Any:
    """A JSON-able, rounded copy of ``value`` (objects become their public fields)."""
    if depth > 6:
        return repr(type(value).__name__)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), DIGITS)
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, np.ndarray):
        return plain(value.tolist(), depth + 1)
    if isinstance(value, dict):
        return {
            str(k): plain(v, depth + 1) for k, v in value.items() if k not in VOLATILE
        }
    if isinstance(value, (list, tuple, set)):
        items = sorted(value, key=repr) if isinstance(value, set) else value
        return [plain(v, depth + 1) for v in items]
    if dataclasses.is_dataclass(value):
        return plain(
            {f.name: getattr(value, f.name) for f in dataclasses.fields(value)},
            depth,
        )
    if hasattr(value, "__dict__"):
        return plain(
            {
                k: v
                for k, v in vars(value).items()
                if not k.startswith("_") and not callable(v)
            },
            depth + 1,
        )
    return repr(type(value).__name__)


def _state(env: Any) -> dict:
    """Agents' and DSO's state after a step."""
    while not hasattr(env, "_agents"):  # GroupedLEM wraps the market twice
        env = env.env
    return {
        "agents": {
            aid: {
                "profit": a.profit,
                "battery": a.battery.energy_level if a.battery else None,
            }
            for aid, a in env._agents.items()
        },
        "dso_balance": env.dso.balance,
    }


def _space(env: Any, aid: str) -> Any:
    """The action space of one agent (or of the group, for GroupedLEM)."""
    spaces = getattr(env, "action_spaces", None)
    return spaces[aid] if spaces else env.action_space[aid]


def _episode(env: Any, steps: int, action_seed: int) -> list[dict]:
    obs, info = env.reset(seed=None)
    record = [{"obs": plain(obs), "info": plain(info)}]
    ids = list(obs)
    for i, aid in enumerate(ids):
        _space(env, aid).seed(action_seed + i)
    for _ in range(steps):
        acts = {aid: _space(env, aid).sample() for aid in ids}
        obs, rew, term, trunc, info = env.step(acts)
        record.append(
            {
                "obs": plain(obs),
                "reward": plain(rew),
                "terminated": plain(term),
                "truncated": plain(trunc),
                "info": plain(info),
                "state": plain(_state(getattr(env, "env", env))),
            }
        )
        done = term.get("__all__") if isinstance(term, dict) else term
        cut = trunc.get("__all__") if isinstance(trunc, dict) else trunc
        if done or cut:
            break
    return record


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def scenarios() -> dict[str, Any]:
    """Name -> function building a fresh environment (seeds set inside)."""
    from utils import create_env_config, create_market_config

    def ieee34_average() -> Any:
        _seed(42)
        return LocalEnergyMarket(create_env_config(seed=42))

    def mesh_seller_async() -> Any:
        _seed(7)
        config = create_env_config(
            seed=7,
            num_agents=4,
            market_config=create_market_config(
                price_mechanism=ClearingMechanism.SELLER,
                enable_partner_preference=False,
                blockchain_difficulty=1,
            ),
            grid_network=GridNetwork(GridTopology.MESH, 4, 300.0, seed=1),
        )
        config["enable_asynchronous_order"] = True
        return LocalEnergyMarket(config)

    def ring_nash_reset_dso() -> Any:
        _seed(3)
        config = create_env_config(
            seed=3,
            num_agents=3,
            market_config=create_market_config(
                price_mechanism=ClearingMechanism.NASH_BARGAINING,
                blockchain_difficulty=1,
            ),
            grid_network=GridNetwork(GridTopology.RING, 3, 200.0, seed=2),
        )
        config["enable_reset_dso_profiles"] = True
        return LocalEnergyMarket(config)

    def grouped_ctce() -> Any:
        from src_thesis.marl.train import GroupedLEM

        _seed(11)
        config = create_env_config(seed=11)
        return GroupedLEM(config)

    return {
        "ieee34_average": ieee34_average,
        "mesh_seller_async": mesh_seller_async,
        "ring_nash_reset_dso": ring_nash_reset_dso,
        "grouped_ctce": grouped_ctce,
    }


def trace() -> dict[str, list[dict]]:
    """Every scenario: two consecutive episodes of 24 steps."""
    out = {}
    for name, build in scenarios().items():
        env = build()
        out[name] = _episode(env, 24, 100) + _episode(env, 24, 200)
    return out


if __name__ == "__main__":
    FILE.write_text(json.dumps(trace(), indent=0, sort_keys=True), encoding="utf-8")
    print(f"recorded {FILE}")
