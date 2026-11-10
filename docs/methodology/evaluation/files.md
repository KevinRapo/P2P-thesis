# What a run saves

Every file a run leaves, and what one record of it looks like. These are the raw layer:
what is not here can only be computed if the numbers it needs are here. The
[tab pages](../../using/studio/experiments/results/index.md) say what is drawn from them.

The templates show one real record of a run with 13 participants, hourly steps and 14
test days, with `trained`, `random`, `zero` and `net_position` on the test days (runs
since 4 Nov 2026 no longer play `random` there). Counts
are for `obs_reward`, 240,000 environment steps, 10 evaluation points, 5 evaluation
episodes, with the tables written since; the step tables' sizes are estimates.

## Three levels

Each number sits on the lowest level that can hold it, and only the first is permanent:

| Level | What it is | Computed | Where |
|---|---|---|---|
| 1 Saved | Raw tables of one run | During the run | this page |
| 2 Indicator | One number per run, policy and test day | When read | [`indicators.py`](../../../core/runner/indicators.py) |
| 3 Comparison | Any runs side by side, or their difference | When read | [`indicators.py`](../../../core/runner/indicators.py), [Validation](../../using/studio/experiments/results/validation.md) |

So an indicator added later still applies to runs already made, if the saved tables hold
what it needs. That is why every test day is kept step by step, for every policy: it adds
no time, since the evaluation holds every step in memory anyway, and a run cannot get
step tables afterwards. It costs about 5 MB per run at 13 participants and hourly steps.

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

Each table below describes one row of its file, one line per column: the column, a real
value, and what it holds. The files have all these columns side by side, up to 300 and
more, so they are wide; read them in a table viewer or the Studio, not as text.

### metrics.csv

| Column | Example | Meaning |
|---|---|---|
| **Progress** | | |
| `iteration` | 480 | |
| `env_steps` | 240000 | |
| `learner_env_steps` | 19920000 | the learner's own count, over epochs and modules |
| `team_return_mean` | 0.5701 | training return, with exploration |
| **Timing, in seconds** | | |
| `sampler_sample_s_mean`, `sampling_s_mean`, `learner_call_s_mean`, `async_learner_update_s_mean`, `train_call_s`, `train_calls_s_total`, `elapsed_s` | | |
| `sampled_steps_per_train_s` | | environment steps per second |
| **Per module**, `P1` ... `P13` (one group in CTCE) | | |
| `P1/total_loss`, `P1/policy_loss`, `P1/vf_loss`, `P1/vf_loss_unclipped`, `P1/vf_explained_var`, `P1/entropy`, `P1/mean_kl_loss`, `P1/num_module_steps_trained`, `P1/gradients_default_optimizer_global_norm`, `P1/clip_fraction` | | |
| **Per module and action part**, in 128 fixed states | | |
| `P1/price/mean`, `P1/price/log_std`, `P1/price/outside` | | |
| `P1/quantity/mean`, `P1/quantity/log_std`, `P1/quantity/outside` | | |
| `P1/side/entropy`, `P1/side/top` | | |
| `P1/partner/entropy`, `P1/partner/top` | | |
| **Over the modules** | | |
| `modules/<metric>_mean`, `modules/<metric>_min`, `modules/<metric>_max` | | the ten module metrics |

### evaluation.csv, heldout.csv

`heldout.csv` has the same columns without `env_steps`.

| Column | Example | Meaning |
|---|---|---|
| `env_steps` | 0 | the evaluation point |
| `policy` | trained | `trained`, `zero`, `net_position`; `random` at step 0 |
| `team_return_mean` | -2.2549 | over the episodes |
| `team_return_std` | 0.5083 | over the episodes |
| `episodes` | 5 | |
| `return/P1` ... `return/P13` | -0.1484 | one column per participant |

### evaluation_episodes.csv, heldout_episodes.csv

`evaluation_episodes` starts with `env_steps`; `heldout_episodes` has `period` instead.

| Column | Example | Meaning |
|---|---|---|
| `policy` | trained | |
| `episode` | 0 | |
| `seed` | 2000 | |
| `day` | 2016-07-01 | |
| `period` | july | |
| `team_return` | -0.0361 | sum of the participants' returns |
| `p2p_kwh` | 23.3047 | traded between participants |
| `preference_kwh` | 0.18 | of it, stage 1 |
| `sold_to_dso_kwh` | 185.9887 | |
| `bought_from_dso_kwh` | 4.4058 | |
| `trade_losses_kwh` | 1.2811 | the market's estimate, eq. 18 |
| `fees` | 0.2591 | eq. 8 |
| `peer_charge` | 0.0 | |
| `grid_import_kwh` | 296.913 | the power flow, whole network |
| `grid_export_kwh` | 290.604 | |
| `grid_losses_kwh` | 32.248 | |
| `voltage_violations` | 0 | buses outside their limits, elements × steps |
| `loading_violations` | 0 | lines and transformers over theirs |
| `not_converged` | 0 | steps |
| `social_welfare` ... `flexibility_utilization` | | the ten KPIs over the day |

### evaluation_agents.csv, heldout_agents.csv

As above, `env_steps` or `period`.

| Column | Example | Meaning |
|---|---|---|
| `policy` | trained | |
| `episode` | 0 | |
| `seed` | 2000 | |
| `day` | 2016-07-01 | |
| `period` | july | |
| `agent` | P1 | |
| `return` | -0.0425 | |
| `profit` | 0.1357 | revenue − cost of its trades − its fees, eq. 14 |
| `bill` | -0.3686 | profit − utility price × deferred demand; + earned |
| `adjusted_bill` | -0.3686 | bill + stored change × `stored_kwh_value` |
| `fees` | 0.02 | what it paid of the grid fees, its loss charge included |
| `loss_kwh` | 0.012 | its share of the step's measured losses (`dso.losses` other than `"trades"`; 0 otherwise); negative is a credit |
| `loss_charge` | 0.004 | of `fees`, what it paid for that share, at the step's utility price |
| `generation_kwh` | 80.1 | its own |
| `demand_kwh` | 19.2 | |
| `bought_kwh` | 2.4086 | peers and DSO together |
| `sold_kwh` | 64.5604 | |
| `peer_bought_kwh` | 1.2 | of it, with peers |
| `peer_sold_kwh` | 8.3 | |
| `preference_kwh` | 0.0 | of it, stage 1 |
| `deferred_demand_kwh` | 1.4534 | demand left uncovered |
| `deferred_supply_kwh` | 1.4056 | surplus spilled |
| `charge_kwh` | 0.0 | energy into its battery |
| `discharge_kwh` | 0.0 | energy out of it |
| `stored_change_kwh` | 0.0 | change of the energy in its battery |

### heldout_steps.csv

Every test day, for every policy. The amounts of `heldout_episodes` for the step, and
what exists only per step.

| Column | Example | Meaning |
|---|---|---|
| `policy`, `episode`, `seed`, `day`, `period` | | as `heldout_episodes` |
| `step` | 12 | |
| `team_reward` | -0.3341 | |
| `p2p_kwh` ... `not_converged` | | the 13 amounts of `heldout_episodes`, for this step |
| `clearing_price` | 0.151 | the last one kept when no peers traded |
| `peer_price` | 0.151 | the same, empty when no peers traded |
| `feed_in_tariff` | 0.0 | |
| `utility_price` | 0.3163 | |
| `min_voltage_pu` | 1.0227 | |
| `max_voltage_pu` | 1.0267 | |
| `max_line_loading_percent` | 5.11 | the power flow's |
| `max_trafo_loading_percent` | 12.4 | |
| `fee_max_line_loading_percent` | 5.11 | what the fees were charged on |

### heldout_agent_steps.csv

Every test day, for every policy. The amounts of `heldout_agents` for the step, and what
exists only per step.

| Column | Example | Meaning |
|---|---|---|
| `policy`, `episode`, `seed`, `day`, `period` | | as `heldout_agents` |
| `step` | 1 | |
| `agent` | P3 | |
| `reward` | -0.0023 | |
| `profit` ... `adjusted_bill` | | the amounts of `heldout_agents`, for this step |
| `order_kwh` | -0.0048 | as the market took it: + sell, − buy, 0 none |
| `order_price` | 0.04 | empty without an order |
| `side` | buy | `buy`, `sell`, `none` |
| `partner` | P5 | a participant or `none` (`DSO` in runs before RP-1h) |
| `partner_index` | 3 | the action's index; empty without an order |
| `partner_mutual` | 0 | 1 if it named this agent back; empty without a peer |
| `action_side`, `action_quantity`, `action_price`, `action_partner` | 1, -0.93, 0.12, 4 | the action's four parts as the policy gave them, before decoding, also when no order was placed: the no-order region is `action_quantity` below $2 \cdot 0.05 - 1 = -0.9$ (RP-7l) |
| `soc` | | after the step, 0 to 1; empty without a battery |
| `reputation` | 0.5189 | after the step, eq. 12 |
| **With the salazar reward, before compression** | | |
| `reward_grid`, `reward_resource`, `reward_trading`, `reward_stability`, `reward_economic`, `reward_boost`, `reward_dso_penalty`, `reward_demand_penalty` | | the eight parts; penalties are stored positive |
| `reward_no_trades` | | instead of the first eight, in a step without trades |

`log_compress(grid + resource + trading + stability + economic + boost − dso penalty −
demand penalty)` is the step's `reward`.

## JSON files

In these examples, `"..."` stands for more entries of the same kind, left out. The values
are from one run of `base_long_p13` (13 participants, hourly steps); paths and the
cluster account are replaced by placeholders.

### run.json

```json
{
  "algorithm": "ppo",
  "paradigm": "dtde",
  "env_class": "core.env.market_env:MarketEnv",
  "env_config": {
    "scenario": "runs/<experiment>/<run>/scenario.json",
    "days": ["2016-01-01", "2016-01-02", "..."],
    "seed": 0,
    "grid_capacity_kwh": 400.0,
    "reward": "bill",
    "observation": "paper",
    "stored_kwh_value": 0.3766,
    "energy_scale": 16.837,
    "reward_scale": 21.09,
    "tariff_range": [0.0, 1.2526]
  },
  "env_config_given": {
    "scenario": "runs/<experiment>/<run>/scenario.json",
    "days": ["2016-01-01", "2016-01-02", "..."],
    "seed": 0,
    "grid_capacity_kwh": 400.0,
    "reward": "bill",
    "...": "..."
  },
  "env_contract": {
    "observation": ["hour_sin", "hour_cos", "clearing_price", "..."],
    "action": { "components": { "...": "..." }, "policy": "factorised over the components" },
    "partners": { "P1": ["..."], "P2": ["..."], "...": "..." },
    "...": "..."
  },
  "agents": ["P1", "P2", "...", "P13"],
  "spaces": { "P1": { "observation": "Box(-10.0, 10.0, (54,), float32)", "...": "..." }, "...": "..." },
  "budget_env_steps": 1200000,
  "seed": 0,
  "eval_every": 120000,
  "eval_seeds": [1000000, 1000001, 1000002, 1000003, 1000004],
  "periodic_evaluation": "evaluation*.csv: the training env_config (training days) on seeds training does not use; not held out",
  "settings": { "clip_param": 0.2, "entropy_coeff": 0.01, "gamma": 0.99, "grad_clip": 0.5, "...": "..." },
  "settings_effective": { "lr": 0.0003, "gamma": 0.99, "lambda_": 0.95, "use_gae": true, "...": "..." },
  "model": {},
  "model_effective": { "vf_share_layers": false, "fcnet_hiddens": [256, 256], "fcnet_activation": "tanh", "...": "..." },
  "num_env_runners": 8,
  "num_gpus": 0,
  "python_hash_seed": "0",
  "versions": { "python": "3.12.15", "ray": "2.51.1", "torch": "2.6.0+cu126", "numpy": "2.4.6", "gymnasium": "1.1.1" },
  "git": { "commit": "fc735317d9ce5ca311a950b348f7fdec0b0a805f", "uncommitted_changes": true },
  "started": "2026-11-05T10:19:02",
  "status": "completed",
  "out_dir": "runs/<experiment>/<run>",
  "env_steps": 1200000.0,
  "iterations": 300,
  "final": { "env_steps": 1200000.0, "team_return_mean": -0.4176, "team_return_std": 1.2077, "episodes": 5.0, "...": "..." },
  "timings": { "evaluation_s": 28.5, "train_calls_s": 9371.5, "ray_init_s": 6.0, "build_s": 22.4, "checkpoint_s": 3.6 },
  "duration_s": 9448.2,
  "finished": "2026-11-05T12:56:36"
}
```

| Field | Meaning |
|---|---|
| `env_config` | as the run used it, with the scales it resolved (`energy_scale`, `reward_scale`, `tariff_range`) |
| `env_config_given` | as given, before the scales |
| `env_contract` | what the environment's numbers mean: the names of the observation, each action part with its bounds and meaning, each agent's partner list, the reward and the scales |
| `spaces` | each agent's observation and action spaces |
| `settings`, `settings_effective` | the PPO settings given; every PPO setting with its value |
| `model`, `model_effective` | the same for the network |
| `git` | the commit the run started from, and whether the working tree had uncommitted changes |
| `final` | the last evaluation of the trained policy |
| `timings` | seconds in Ray's start-up, the build, the training calls, the evaluation and the checkpoint |

### status.json

```json
{
  "state": "completed",
  "index": 3,
  "budget": 1200000,
  "started": "2026-11-05T10:18:51",
  "updated": "2026-11-05T12:56:57",
  "finished": "2026-11-05T12:56:57",
  "duration_s": 9487.1,
  "host": "blackwell1.hpclocal",
  "pid": 3014194,
  "create_time": 1793866729.18,
  "slurm_job": "1075495_3"
}
```

`state` is `queued`, `running`, `completed`, `failed` or `stopped`. `index` is the run's
place in the grid of runs, `pid` and `create_time` identify the process that ran it, and
`slurm_job` is there on the cluster only.

### experiment.json

```json
{
  "name": "base_long_p13",
  "algorithms": ["ppo"],
  "paradigms": ["ctce", "dtde", "ctde"],
  "seeds": [0, 1, 2],
  "budget": 1200000,
  "scenario": { "name": "lv_rural3_p13", "grid": { "code": "1-LV-rural3--2-sw", "...": "..." }, "...": "..." },
  "env": "market",
  "train_days": ["2016-01-01", "2016-01-02", "..."],
  "test_days": ["2016-07-01", "2016-07-02", "..."],
  "test_periods": { "july": ["2016-07-01", "..."] },
  "env_config": { "grid_capacity_kwh": 400.0, "reward": "bill", "observation": "paper", "...": "..." },
  "variants": { "base": { "scenario": { "dso": { "prices": "de_2024" } } } },
  "eval_points": 10,
  "eval_episodes": 5,
  "training": { "ppo": { "lr": 0.0003, "gamma": 0.99, "lambda_": 0.95, "...": "..." } },
  "model": {},
  "max_parallel": 9,
  "torch_threads": 1,
  "num_env_runners": 8,
  "ray_thread_caps": true,
  "resources": { "cpus": 10, "mem_gb": 24, "minutes": 240, "node": "blackwell1" },
  "test": {},
  "description": "..."
}
```

`scenario` is the scenario itself. `variants` lists every variant at the top of the
experiment and is empty in a run's own copy.

### scenario.json

```json
{
  "name": "lv_rural3_p13",
  "grid": {
    "code": "1-LV-rural3--2-sw",
    "day": "2016-06-15",
    "step_hours": 1.0,
    "background": "profiles",
    "v_min_pu": 0.95,
    "v_max_pu": 1.05,
    "...": "..."
  },
  "participants": [
    { "id": "P1", "bus": "LV3.101 Bus 1", "owns": ["LV3.101 Load 23", "LV3.101 Load 152", "LV3.101 SGen 6"], "battery": null },
    "..."
  ],
  "market": {
    "mechanism": "average",
    "min_price": 0.0,
    "max_price": 1.0,
    "min_quantity": 0.0,
    "max_quantity": 100.0,
    "partner_preference": true,
    "...": "..."
  },
  "dso": {
    "prices": "synthetic_day",
    "fees_charged": true,
    "fee_buyer_share": 0.5,
    "loss_factor": 0.03,
    "congestion_factor": 0.5,
    "...": "..."
  }
}
```

`grid` holds the network, the day, the step length, the voltage and line limits, the
method and the graph settings. `market` also holds the reputation settings and the
seed. `dso` holds the prices as given (a file name, flat tariffs or the series), the
peer charge and the fee settings.

The prices themselves are not saved with the run when they are given by name: they
stay in `config/data/`.

### slurm.json

```json
{
  "array_id": "1075495",
  "submitted": "2026-11-05T10:18:48",
  "partition": "short",
  "account": "<account>",
  "resources": { "cpus": 10, "mem_gb": 24, "minutes": 240, "node": "blackwell1" },
  "tasks": {
    "ppo_ctce_s0_base": "1075495_0",
    "ppo_ctce_s1_base": "1075495_1",
    "...": "..."
  }
}
```

`tasks` maps each run's name to its SLURM task.

## What a table cannot give

No file holds these, so nothing can compute them later:

- loading per line, voltage per bus;
- which participant's share of the power flow's exchange;
- the periodic evaluation step by step: its step tables are never written;
- the prices of a run started by a price file's name: they stay in `config/data/`, but
  `feed_in_tariff` and `utility_price` per step record what it traded at.

Runs from before these tables have no step tables, no KPIs and none of the new amounts:
their indicators stay empty.
