# MARLEM RL

The reinforcement-learning part of MARLEM (Salazar et al.), validated on its own:
the training paradigms (CTCE, CTDE, DTDE) and algorithms (PPO, APPO, SAC),
without the local energy market.

`core/rl/` holds the RL code copied verbatim from the original repository
(`src/environment/` at `main` 15d6715): `base.py`, `ctce.py`, `ctde.py`,
`train.py`, `inference.py`.
