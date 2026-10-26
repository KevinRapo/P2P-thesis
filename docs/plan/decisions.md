# Decision log

One row per decision of the [market plan](market.md) (`MP-`) and the
[RL plan](rl.md) (`RP-`). The plan poses the decision and its options; this log
keeps what was chosen. *Evidence* is the check, run or probe that informed it;
*Implemented in* is the code and the [full cycle](../full-cycle.md) section, or
"no code change". How the pages fit together: [Plans](index.md).

## Market (`MP-`)

| ID | Decision | Reason | Evidence | Implemented in | Date |
|---|---|---|---|---|---|

## RL (`RP-`)

| ID | Decision | Reason | Evidence | Implemented in | Date |
|---|---|---|---|---|---|
| RP-3h | The continuous action parts: one learned log std per part for every state (MAPPO's `DiagGaussian`), and each part's mean through tanh (`free_log_std_parts`, `bound_mean` in [rl_defaults.py](../../core/rl_defaults.py)); no bounds on the log std | RLlib's state-dependent log std shrank faster than the categorical part it depends on was decided, after which the mean could not reach its target (probe 9: log std to −5.5, the level stuck at 0.1–0.35). The state-independent log std moves at most about the learning rate per step, slow enough for the mean to follow; the bounded mean keeps it inside the action's bounds, where the clipped reward is not flat. Bounding the log std alone (variant A) did not help | Probe comparison of 26 Oct 2026, fast preset, 3 seeds (`runs/@taltech/probe_methods_scores.csv`): probe 9 in CTDE/DTDE 0/6 (RLlib) → 6/6 (SM); CTDE/DTDE 47/60 → 56/60 overall. Not solved by any variant: probe 6, CTCE | [modules.py](../../core/rl/modules.py), [rl_defaults.py](../../core/rl_defaults.py) | 26 Oct 2026 |
| RP-4a | The KL between the collecting and the updated policy is computed and logged (`mean_kl_loss`) with weight 0 in the loss: `use_kl_loss=True`, `kl_coeff=0.0` | PPO's most direct measure of each update's size; RLlib computes it only with `use_kl_loss=True`, and with coefficient 0 its adaptive weight stays 0. L-07's risk (a non-finite KL making the loss NaN unnoticed) is covered: training stops on any non-finite metric | Discussion of 24-25 Oct 2026; probe 9's frozen level, where the update size is the question | [rl_defaults.py](../../core/rl_defaults.py), [config.py](../../core/rl/config.py) | 25 Oct 2026 |
| RP-3e | CTDE uses each agent's own reward, one central critic per agent (input $[o_i, o_1, \dots, o_N]$) and one actor per agent (input $o_i$); no parameter sharing for now. A team-reward CTDE, a shared critic and group-wise policy sharing are in the parking lot | The households are self-interested, each paying its own bill, and [P2] defines CTDE on each agent's own return (eq. 18-19). With individual rewards every critic learns a different value function, so nothing is duplicated; the per-agent central critic for agents with their own rewards is MADDPG's design (Lowe et al. 2017). A shared critic would cost the same operations per step and could only gain data efficiency, at the risk of interference between different households | Discussion of 24 Oct 2026 (MAPPO's shared critic assumes a team reward, Yu et al. 2022 §3) | no code change: [ctde.py](../../core/rl/ctde.py), [config.py](../../core/rl/config.py) | 24 Oct 2026 |
