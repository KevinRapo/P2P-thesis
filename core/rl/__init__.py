"""The RL layer: the three paradigms on RLlib's own algorithms and modules.

It imports no market module: the environment arrives as a class. What each file
fixes is in its docstring; the issue IDs are those of the validation document
(``docs/validation/rl.md``). The original code and its annotations live on the
``clean`` branch.

    state.py          the global state: every agent's observation joined, in agent order
    ctce.py           CTCE: all agents as one agent (CTCEEnv)
    ctde.py           CTDE: the global state in each observation (CTDEEnv), and
                      RLlib's PPO module with the actor on the agent's own part
    config.py         the algorithm configuration of one algorithm and paradigm
    policy.py         acting with a trained module, baselines, evaluation
    train.py          one run: budget in environment steps, record, checkpoint
"""

from core.rl.config import Algorithm, Paradigm, build_config
from core.rl.policy import Evaluation, Policy, evaluate, evaluation, rollout
from core.rl.train import Run, load_policy, train

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
