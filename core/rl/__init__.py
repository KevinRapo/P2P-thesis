"""The RL layer: the three paradigms on RLlib's own algorithms and modules.

It imports no market module: the environment arrives as a class. What each file
fixes is in its docstring; the issue IDs are those of the validation document
(``docs/validation/rl.md``). The original code and its annotations live on the
``clean`` branch.

    grouping.py       all agents as one agent (CTCE, CTDE), spaces in agent order
    ctde_modules.py   CTDE: RLlib's modules with one actor network per agent
    defaults.py       the default hyperparameters and network settings (no Ray)
    config.py         the algorithm configuration of one algorithm and paradigm
    policy.py         acting with a trained module, baselines, evaluation
    train.py          one run: budget in environment steps, record, checkpoint
"""

import importlib

# The names below are loaded when first used, so ``core.rl.defaults`` can be read
# without Ray and torch (the runner's status and the Studio read it).
_NAMES = {
    "Algorithm": "core.rl.config",
    "Paradigm": "core.rl.config",
    "build_config": "core.rl.config",
    "Evaluation": "core.rl.policy",
    "Policy": "core.rl.policy",
    "evaluate": "core.rl.policy",
    "evaluation": "core.rl.policy",
    "rollout": "core.rl.policy",
    "Run": "core.rl.train",
    "load_policy": "core.rl.train",
    "train": "core.rl.train",
}

__all__ = [
    "Algorithm",
    "Paradigm",
    "Policy",
    "Run",
    "build_config",
    "Evaluation",
    "evaluate",
    "evaluation",
    "load_policy",
    "rollout",
    "train",
]


def __getattr__(name: str):
    if name not in _NAMES:
        raise AttributeError(f"module 'core.rl' has no attribute {name!r}")
    return getattr(importlib.import_module(_NAMES[name]), name)
