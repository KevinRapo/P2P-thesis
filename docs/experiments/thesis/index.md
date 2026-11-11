# Thesis experiments

> The runs the thesis reports, one page each: its question and expected result,
> its scenario, the arms, every setting with where its value comes from and
> whether it is decided, what is measured, and the results. A run starts once its
> open settings are decided; its results are added to its page.

| Experiment | Question | Status |
|---|---|---|
| [Reward and observation](reward-obs.md) | Do agents trained with our reward and observation do better for the participants than with the original's? | Set up, not yet outlined |

Each experiment is a file in [config/experiments/](../../../config/experiments/). The
starting point is [`thesis.json`](../../../config/experiments/thesis.json), PPO in CTDE on
the scenario [`thesis_rural1.json`](../../../config/scenarios/thesis_rural1.json)
(`1-LV-rural1--2-sw`, all 13 participants, the power flow, `dso.losses` `bcdla`), to be
edited. The reward and observation experiment is archived as
[`thesis_reward_obs.json`](../../../config/archive/experiments/thesis_reward_obs.json).
How to run one: [Starting and following runs](../../using/running/runs.md).
