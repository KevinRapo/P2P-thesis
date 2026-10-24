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
| RP-3e | CTDE uses each agent's own reward, one central critic per agent (input $[o_i, o_1, \dots, o_N]$) and one actor per agent (input $o_i$); no parameter sharing for now. A team-reward CTDE, a shared critic and group-wise policy sharing are in the parking lot | The households are self-interested, each paying its own bill, and [P2] defines CTDE on each agent's own return (eq. 18-19). With individual rewards every critic learns a different value function, so nothing is duplicated; the per-agent central critic for agents with their own rewards is MADDPG's design (Lowe et al. 2017). A shared critic would cost the same operations per step and could only gain data efficiency, at the risk of interference between different households | Discussion of 24 Oct 2026 (MAPPO's shared critic assumes a team reward, Yu et al. 2022 §3) | no code change: [ctde.py](../../core/rl/ctde.py), [config.py](../../core/rl/config.py) | 24 Oct 2026 |
