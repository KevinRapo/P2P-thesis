# MARLEM RL

The reinforcement-learning part of MARLEM (Salazar et al.), validated on its own:
the training paradigms (CTCE, CTDE, DTDE) and algorithms (PPO, APPO, SAC),
without the local energy market.

```
core/rl/     the RL code from the original repository, isolated from the market
core/fixed/  the RL layer rebuilt on RLlib's own algorithms and modules, issues fixed
core/envs/   small test environments with a known best return, and MPE2 simple_spread
notebooks/   call core/ only, one folder per implementation:
  original/  tests core/rl/: probe_paradigms.ipynb checks each paradigm piece by
             piece; simple_spread.ipynb trains every paradigm and algorithm on
             Farama's simple_spread and shows the agents; validate_rl.ipynb compares
             how fast they learn
  fixed/     tests core/fixed/: probe_paradigms.ipynb and simple_spread.ipynb, the
             same tests for all nine combinations, budgets in environment steps
```

What is wrong with the RL layer, and what the tests show:
[docs/validation/rl.md](../docs/validation/rl.md).

Run the notebooks with the `marlem` conda env as kernel (`simple_spread.ipynb` also
needs `pip install mpe2`). See `AGENTS.md` for the
rules of this folder.

## Automated tests

With the `marlem` Conda environment selected, run `python -m pytest -q` from
this folder, or use VS Code's Testing panel. `pytest.ini` restricts discovery
to `tests/` and adds the parent repository root to Python's import path.

The initial suite checks probe reset reproducibility, observation spaces,
two-step rewards and episode endings, and per-agent action routing. These are
deterministic checks of the environments; they do not establish that the RL
algorithms learn. Continue using the probe notebooks to validate learning.

## Location and imports

This folder contains the former `marlem-rl` worktree, including its uncommitted
benchmark files and saved `runs/` (still ignored by Git). The internal layout
is unchanged. Use `RL.core.*` imports; `core.*` belongs to the market.
Notebooks locate this folder automatically from the clean root or below it;
restart existing notebook kernels after switching to the copied notebooks.

From `marlem-clean`, run `python -m pytest` for both layers or
`python -m pytest RL/tests` for RL alone; from this folder, run
`python -m pytest`. The speed benchmark reads
`../notebooks/results/market_step.csv`. RL still uses its test environments;
the market and RL implementations have not been connected.

Saved run records and checkpoint bytes are preserved. `load_policy` accepts their
pre-migration `core.*` names while loading; new runs use `RL.core.*`.

Migration checks found that `runs/probes_thorough/ppo_ctde_p1` already has an
empty saved module set in the source worktree. It is copied unchanged; loading
that existing checkpoint does not produce an actionable policy.
