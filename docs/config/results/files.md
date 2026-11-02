# Saved files

Every file a run leaves, and what one record of it looks like. These are the raw layer:
what is not here can only be computed if the numbers it needs are here. The
[tab pages](index.md) say what is drawn from them.

The templates show one real record of a run with 13 participants, hourly steps and 14
test days, with `trained`, `random`, `zero` and `net_position` on the test days. Counts
are for `obs_reward`, 240,000 environment steps, 10 evaluation points, 5 evaluation
episodes, with the tables written since; the step tables' sizes are estimates.

## The folder

```text
runs/<experiment>/
├── experiment.json              the whole experiment, variants included
├── scenario.json                the base scenario
├── slurm.json                   cluster: the array and its tasks
├── slurm/                       cluster: submitit's scripts and logs; not synced
├── worker.json, worker.log      this PC: the process running the queue
└── <run>/                       <algorithm>_<paradigm>_s<seed>[_<variant>]
    ├── experiment.json          this run's arm
    ├── scenario.json            this run's scenario, the file it reads
    ├── run.json                 what was run, and its outcome
    ├── status.json              its state
    ├── log.txt                  this PC: its output
    ├── metrics.csv              the learner, per iteration
    ├── evaluation.csv           periodic evaluation: return per policy
    ├── evaluation_episodes.csv  periodic evaluation: per day
    ├── evaluation_agents.csv    periodic evaluation: per day and participant
    ├── heldout.csv              test days: return per policy
    ├── heldout_episodes.csv     test days: per day
    ├── heldout_agents.csv       test days: per day and participant
    ├── heldout_steps.csv        test days: per step
    ├── heldout_agent_steps.csv  test days: per step and participant
    └── checkpoint/              the trained policy; not synced
```

## What each table holds

| File | One row per | Rows | Columns | Size |
|---|---|---|---|---|
| `metrics.csv` | iteration | 480 | 302 | 2 MB |
| `evaluation.csv` | policy, evaluation point | 14 | 18 | 5 KB |
| `evaluation_episodes.csv` | policy, point, episode | 70 | 18 | 14 KB |
| `evaluation_agents.csv` | policy, point, episode, participant | 910 | 16 | 160 KB |
| `heldout.csv` | policy | 3 | 17 | 1 KB |
| `heldout_episodes.csv` | policy, test day | 42 | 18 | 8 KB |
| `heldout_agents.csv` | policy, test day, participant | 546 | 16 | 90 KB |
| `heldout_steps.csv` | policy, test day, step | 96 per day | 29 | 25 KB per day |
| `heldout_agent_steps.csv` | policy, test day, step, participant | 1248 per day | 32 to 41 | 350 KB per day |

## Tables

Every amount in a day's row is the sum over its steps. Money is in the scenario's unit,
EUR here. Returns and rewards are in the reward's own units.

### metrics.csv

```text
iteration: 480
env_steps: 240000
learner_env_steps: 19920000           the learner's own count, over epochs and modules
team_return_mean: 0.5701                training return, with exploration

# timing, in seconds
sampler_sample_s_mean, sampling_s_mean, learner_call_s_mean,
async_learner_update_s_mean, train_call_s, train_calls_s_total, elapsed_s
sampled_steps_per_train_s                environment steps per second

# per module: P1 ... P13 (one group in CTCE)
P1/total_loss
P1/policy_loss
P1/vf_loss
P1/vf_loss_unclipped
P1/vf_explained_var
P1/entropy
P1/mean_kl_loss
P1/num_module_steps_trained
P1/gradients_default_optimizer_global_norm
P1/clip_fraction

# per module and action part, in 128 fixed states
P1/price/mean        P1/price/log_std     P1/price/outside
P1/quantity/mean     P1/quantity/log_std  P1/quantity/outside
P1/side/entropy      P1/side/top
P1/partner/entropy   P1/partner/top

# the ten module metrics over the modules
modules/<metric>_mean, modules/<metric>_min, modules/<metric>_max
```

### evaluation.csv, heldout.csv

`heldout.csv` has the same columns without `env_steps`.

```text
env_steps: 0                  the evaluation point
policy: trained               trained, zero, net_position; random at step 0
team_return_mean: -2.2549     over the episodes
team_return_std: 0.5083       over the episodes
episodes: 5
return/P1: -0.1484            ... to return/P13
```

### evaluation_episodes.csv, heldout_episodes.csv

`evaluation_episodes` starts with `env_steps`; `heldout_episodes` has `period` instead.

```text
policy: trained
episode: 0
seed: 2000
day: 2016-07-01
period: july
team_return: -0.0361          sum of the participants' returns
p2p_kwh: 23.3047              traded between participants
preference_kwh: 0.18          of it, stage 1
sold_to_dso_kwh: 185.9887
bought_from_dso_kwh: 4.4058
trade_losses_kwh: 1.2811      the market's estimate, eq. 18
fees: 0.2591                  eq. 8
peer_charge: 0.0
grid_import_kwh: 296.913      the power flow, whole network
grid_export_kwh: 290.604
grid_losses_kwh: 32.248
voltage_violations: 0         buses outside their limits, elements × steps
loading_violations: 0         lines and transformers over theirs
not_converged: 0              steps
social_welfare ... flexibility_utilization: the ten KPIs over the day
```

### evaluation_agents.csv, heldout_agents.csv

As above, `env_steps` or `period`.

```text
policy: trained
episode: 0
seed: 2000
day: 2016-07-01
period: july
agent: P1
return: -0.0425
profit: 0.1357                revenue − cost of its trades − its fees, eq. 14
bill: -0.3686                 profit − utility price × deferred demand; + earned
adjusted_bill: -0.3686        bill + stored change × stored_kwh_value
fees: 0.02                    what it paid of the grid fees
generation_kwh: 80.1          its own
demand_kwh: 19.2
bought_kwh: 2.4086            peers and DSO together
sold_kwh: 64.5604
peer_bought_kwh: 1.2          of it, with peers
peer_sold_kwh: 8.3
preference_kwh: 0.0           of it, stage 1
deferred_demand_kwh: 1.4534   demand left uncovered
deferred_supply_kwh: 1.4056   surplus spilled
charge_kwh: 0.0               energy into its battery
discharge_kwh: 0.0            energy out of it
stored_change_kwh: 0.0        change of the energy in its battery
```

### heldout_steps.csv

Every test day, for every policy. The amounts of `heldout_episodes` for the step, and
what exists only per step.

```text
policy, episode, seed, day, period: as heldout_episodes
step: 12
team_reward: -0.3341
p2p_kwh ... not_converged: the 13 amounts of heldout_episodes, for this step
clearing_price: 0.151         the last one kept when no peers traded
peer_price: 0.151             the same, empty when no peers traded
feed_in_tariff: 0.0
utility_price: 0.3163
min_voltage_pu: 1.0227
max_voltage_pu: 1.0267
max_line_loading_percent: 5.11       the power flow's
max_trafo_loading_percent: 12.4
fee_max_line_loading_percent: 5.11   what the fees were charged on
```

### heldout_agent_steps.csv

Every test day, for every policy. The amounts of `heldout_agents` for the step, and what
exists only per step.

```text
policy, episode, seed, day, period: as heldout_agents
step: 1
agent: P3
reward: -0.0023
profit ... adjusted_bill: the amounts of heldout_agents, for this step
order_kwh: -0.0048            as the market took it: + sell, − buy, 0 none
order_price: 0.04             empty without an order
side: buy                     buy, sell, none
partner: P5                   a participant, DSO, none
partner_index: 3              the action's index; empty without an order
partner_mutual: 0             1 if it named this agent back; empty without a peer
soc: (empty)                  after the step, 0 to 1; empty without a battery
reputation: 0.5189            after the step, eq. 12

# with the salazar reward, before compression: the first eight, or reward_no_trades
reward_grid, reward_resource, reward_trading, reward_stability, reward_economic
reward_boost, reward_dso_penalty, reward_demand_penalty
reward_no_trades
```

`log_compress(grid + resource + trading + stability + economic + boost − dso penalty −
demand penalty)` is the step's `reward`; penalties are stored positive.

## JSON files

### run.json

```text
algorithm: ppo
paradigm: dtde
seed: 0
env_class: core.env.market_env:MarketEnv
env_config:                   as the run used it, with the scales it resolved
  scenario, days, seed, grid_capacity_kwh, reward, observation,
  energy_scale, reward_scale, tariff_range
env_config_given:             as given, before the scales
env_contract:
  observation                 the names of the observation
  action                      each part, with its bounds and meaning
  partners                    each agent's partner list
  reward, scales
agents, spaces                each agent's observation and action spaces
budget_env_steps, eval_every, eval_seeds, periodic_evaluation
settings                      the PPO settings given
settings_effective            every PPO setting with its value
model, model_effective        the same for the network
num_env_runners, num_gpus, python_hash_seed
versions                      python, ray, torch, numpy, gymnasium
git                           commit, uncommitted_changes
out_dir, started, finished, status, env_steps, iterations, duration_s
final                         the last evaluation of the trained policy
timings                       ray_init_s, build_s, train_calls_s, evaluation_s,
                              checkpoint_s
```

### status.json

```text
state: completed              queued, running, completed, failed, stopped
index: 1                      its place in the grid of runs
budget: 4800
started, finished, updated, duration_s
host: green19.hpclocal
pid, create_time              the process
slurm_job: 1062914_1          cluster
```

### experiment.json

```text
name, description, env
scenario                      the scenario itself
algorithms, paradigms, seeds, budget
train_days, test_days, test_periods
env_config
variants                      at the top: every variant; in a run: empty
eval_points, eval_episodes
training, model
max_parallel, torch_threads, num_env_runners, ray_thread_caps
resources                     cpus, mem_gb, minutes, node
test
```

### scenario.json

```text
name
grid                          code, day, step_hours, background, voltage and line
                              limits, method, graph settings
participants                  id, bus, owns, battery
market                        mechanism, price and quantity limits, partner
                              preference, reputation settings, seed
dso                           prices, as given: a file name, flat tariffs or the
                              series; peer charge, fee settings
```

The prices themselves are not saved with the run when they are given by name: they
stay in `config/data/`.

### slurm.json

```text
array_id: 1062914
submitted, partition, account
resources                     cpus, mem_gb, minutes, node
tasks                         run name -> SLURM task
```

## What a table cannot give

No file holds these, so nothing can compute them later:

- loading per line, voltage per bus;
- which participant's share of the power flow's exchange;
- the periodic evaluation step by step: its step tables are never written;
- the prices of a run started by a price file's name: they stay in `config/data/`, but
  `feed_in_tariff` and `utility_price` per step record what it traded at.

Runs from before these tables have no step tables, no KPIs and none of the new amounts:
their indicators stay empty.
