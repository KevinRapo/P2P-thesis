# The run contract

> What a run fixes, records and reproduces: the scales, `run.json`, the two
> evaluations, the seed, and the first live check of the runner and the cluster.

**Scales.** `MarketEnv` computes the energy scale E from its days and the reward
scale from E. A held-out environment built from the test days would compute a
different E, and observations and rewards would mean different things in training
and in the held-out evaluation. So the scales are resolved once per run
(`MarketEnv.resolved_config`, [train.py](../../core/rl/train.py)), trains and
evaluates with them, records them in `run.json`, and the runner's held-out
evaluation reuses them ([`heldout_env_config`](../../core/runner/launch.py)); a
restored policy is built from the same record. Monetary and physical results
(`profit`, `bill`, kWh, grid amounts) are reported in the infos and tables
independently of the scaled return.

**Run record (`run.json`).** `env_config` (resolved, with the
scales) and `env_config_given`; `env_contract` (observation names, action parts
and their encoding, the partner mapping per agent, the scales); `agents` and each agent's observation and action `spaces`;
`settings_effective` (every PPO setting with the value it ran with, given or
RLlib's default, and the rollout fragment length); `model_effective` (the full
network config); with the existing seed, `PYTHONHASHSEED`, versions and git
commit.

**Two evaluations.** `evaluation*.csv` is the *periodic* evaluation during
training: the trained policy and baselines (random, zero, net position) on the
training configuration, i.e. the training days, with seeds training does not use.
It shows whether the policy learns; it is not held out. `heldout*.csv` (the
runner, after training) plays every test period day by day, the battery carried
over within a period: the genuine held-out evaluation. The Studio's Results page
labels them so.

### Reproducibility

The same seed repeats a run on one machine
([test_7_same_seed_same_run.py](../../tests/rl/test_7_same_seed_same_run.py)). That
takes two things:

| Cause of a difference | Effect | Fix |
|---|---|---|
| RLlib given the per-agent modules as a set | Built, and given their initial weights, in an order that changes with every process | A list in agent order ([config.py](../../core/rl/config.py)) |
| RLlib keeps agent ids in sets while sampling and batching | Python's per-process hash seed changes multi-agent runs | `PYTHONHASHSEED=0` in every runner job, local and SLURM ([launch.py](../../core/runner/launch.py)); `run.json` records it |

Across machines, floating-point rounding differs slightly between CPUs and
libraries and training amplifies it, so identical results are expected on one
machine and statistically equivalent ones across machines. Runs started from a
notebook do not fix the hash seed unless the notebook sets `PYTHONHASHSEED` for the
processes it starts.

### Market, runner and cluster: a live check

Run on 21 Oct 2026 on this PC (Windows, Ray 2.51.1, torch 2.9.0 CPU) and on TalTech.

- **TalTech, live:** `market_ppo --profile test` from this PC through the checkout
  `~/marlem-v2`: SLURM array 1046341, three tasks (CTCE, CTDE, DTDE), 4
  CPUs each, three environment runners per run, all completed in under 3 minutes,
  synced to `runs/@taltech/market_ppo--test`. Each `run.json` records the
  training-day scales (E = 18.989 kWh, reward scale 5.697), the partner mapping,
  the effective PPO settings and commit a3f82ce; the held-out evaluation used the
  same scales (the zero baseline's held-out return, −13.81, is identical in all
  three runs). One batch of 2,400 steps is a pipeline check, not a result: held-out
  team return CTCE −13.26, CTDE −13.66, DTDE −11.75 against zero −13.81 and net
  position −7.61.
- **SLURM submission generation:** `tests/runner/test_slurm.py` and the live
  submission above; `python -m core.runner check config/experiments/market_ppo.json
  --target taltech` reported ready with both checkouts at one commit.
- **Studio:** the quick settings of the Experiments page are tested at the adapter
  (`test_quick_settings_read_and_rewrite_the_editors_json`).

### Known limit

- Ray's start-up occasionally fails when memory is short (several runs in parallel
  each start their own Ray); run fewer in parallel if it happens.
