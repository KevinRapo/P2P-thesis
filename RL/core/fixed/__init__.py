"""The fixed RL layer: the three paradigms on RLlib's own algorithms and modules.

Kept apart from the original (``core/rl/``) so the two can be compared. What each
file fixes is in its docstring; the issue IDs are those of the validation
document (``docs/validation/rl.md`` on the clean branch).

    grouping.py       all agents as one agent (CTCE, CTDE), spaces in agent order
    ctde_modules.py   CTDE: RLlib's modules with one actor network per agent
    config.py         the algorithm configuration of one algorithm and paradigm
    policy.py         acting with a trained module, baselines, evaluation
    train.py          one run: budget in environment steps, record, checkpoint
"""

from RL.core.fixed.config import Algorithm, Paradigm, build_config
from RL.core.fixed.policy import Policy, evaluate, rollout
from RL.core.fixed.train import Run, load_policy, train

__all__ = [
    "Algorithm",
    "Paradigm",
    "Policy",
    "Run",
    "build_config",
    "evaluate",
    "load_policy",
    "rollout",
    "train",
]
