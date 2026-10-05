# RL testbench code map

Standalone validation ground for MARLEM's learning layer (plan:
`docs_thesis/thesis/validation/rl-testbench.md`). It trains MARLEM's own
`RLTrainer` (`src_thesis/marl/train.py`), which takes the environment as an
argument (decision D-16); there is no second trainer.

| File | Responsibility | State |
|---|---|---|
| `cases.py` | The cases (CartPole with one agent, MultiAgentCartPole, Simple Spread) and `trainer()`, which builds `RLTrainer` for a case, algorithm and paradigm | done |
| `evaluation.py` | Held-out and random-policy scoring | milestone 1 |
| `reporting.py` | Run manifest, with the experiment layer's code and package fingerprints | done |
| `__main__.py` | Command line | milestone 1 |

The package imports from MARLEM only `marl.train`, `marl.base` and
`experiments.models`; a test enforces it.
