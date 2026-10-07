# MARLEM RL

The reinforcement-learning part of MARLEM (Salazar et al.), validated on its own:
the training paradigms (CTCE, CTDE, DTDE) and algorithms (PPO, APPO, SAC),
without the local energy market.

```
core/rl/     the RL code from the original repository, isolated from the market
core/envs/   small test environments with a known best return
notebooks/   call core/ only: validate_rl.ipynb trains every paradigm on them
```

Run the notebooks with the `marlem` conda env as kernel. See `AGENTS.md` for the
rules of this branch.
