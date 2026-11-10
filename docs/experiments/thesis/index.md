# Thesis experiments

> The runs the thesis reports, one page each: its question and expected result,
> its scenario, the arms, every setting with where its value comes from and
> whether it is decided, what is measured, and the results. A run starts once its
> open settings are decided; its results are added to its page.

| Experiment | Question | Status |
|---|---|---|
| [Grid methods](grid-methods.md) | When agents learn under each grid method's fees, which method leads to less physical stress on the real network, and whose fees follow that stress? The main result | Outline: settings listed, several open |
| [Reward and observation](reward-obs.md) | Do agents trained with our reward and observation do better for the participants than with the original's? | Set up, not yet outlined |

Each experiment is a file in [config/experiments/](../../../config/experiments/):
[`thesis_grid_methods.json`](../../../config/experiments/thesis_grid_methods.json)
and [`thesis_reward_obs.json`](../../../config/experiments/thesis_reward_obs.json).
How to run one: [Starting and following runs](../../using/running/runs.md).
