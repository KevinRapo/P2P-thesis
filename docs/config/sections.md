# Sections

> Every configuration file and section, as raw JSON. An overview for now: the
> examples are copies, taken on 31 Oct 2026 from
> [`validate_market.json`](../../config/scenarios/validate_market.json),
> [`synthetic_day.json`](../../config/data/synthetic_day.json) and
> [`day_end.json`](../../config/experiments/day_end.json), with every setting written
> out. The files themselves are what runs read.

A setting left out of a file takes its default. The values shown are the defaults,
except those a section lists as the file's own. Below each example: what a `null`
or a missing setting becomes, and how it is computed.

A scenario is the world: the network, the participants, the market and the DSO. An
experiment says what is done in it. Price files hold the DSO's tariffs.

| File | Folder | Says |
|---|---|---|
| Scenario | [`config/scenarios/`](../../config/scenarios/validate_market.json) | The network, participants, market rules and DSO |
| Prices | [`config/data/`](../../config/data/synthetic_day.json) | The DSO's tariffs per market step |
| Experiment | [`config/experiments/`](../../config/experiments/day_end.json) | Days, RL settings, seeds, arms and how the runs are run |

## Scenario

One JSON object with `name` and four sections:

```json
{
  "name": "validate_market",
  "grid": {},
  "participants": [],
  "market": {},
  "dso": {}
}
```

### grid

```json
{
  "code": "1-LV-rural1--0-sw",
  "day": "2016-06-15",
  "step_hours": 1.0,
  "background": "profiles",
  "v_min_pu": 0.95,
  "v_max_pu": 1.05,
  "line_max_percent": 100.0,
  "method": "powerflow",
  "graph_capacity": "paper",
  "graph_total_kw": null
}
```

`graph_total_kw`: `null` is the sum of the line ratings. It is only read with
`method` `"graph"` and `graph_capacity` `"paper"`, where each line `e` of length
`ℓ_e` gets `C_e = C_total · (1/ℓ_e) / Σ_k (1/ℓ_k)`.

### participants

One entry per participant. `battery` is `null` without one.

```json
[
  {
    "id": "P1",
    "bus": "LV1.101 Bus 7",
    "owns": ["LV1.101 Load 9", "LV1.101 SGen 1"],
    "battery": {
      "capacity_kwh": 10,
      "min_soc": 0.1,
      "max_soc": 0.9,
      "charge_efficiency": 0.95,
      "discharge_efficiency": 0.95,
      "initial_soc": 0.5,
      "max_power_kw": null
    }
  },
  {
    "id": "P2",
    "bus": "LV1.101 Bus 8",
    "owns": ["LV1.101 Load 2", "LV1.101 SGen 4"],
    "battery": null
  }
]
```

`max_power_kw`: `null` is no power limit, so only the SoC window and the efficiencies
bound what the battery takes or gives in a step. `capacity_kwh` has no default.
`owns` defaults to `[]`.

### market

```json
{
  "mechanism": "average",
  "min_price": 0.0,
  "max_price": 1.0,
  "min_quantity": 0.0,
  "max_quantity": 100.0,
  "price_decimals": 2,
  "partner_preference": true,
  "partner_reputation_weight": 0.5,
  "bid_margin": 0.3,
  "bid_jitter": 0.1,
  "seed": 0,
  "reliability_weight": 0.3,
  "fairness_weight": 0.2,
  "grid_weight": 0.5,
  "reputation_decay": 0.8
}
```

The file's own value: `partner_preference`, whose default is `false`.

### dso

```json
{
  "feed_in_tariff": 0.08,
  "utility_price": 0.3,
  "prices": "synthetic_day",
  "fees_charged": true,
  "fee_buyer_share": 0.5,
  "loss_factor": 0.03,
  "congestion_factor": 0.5,
  "congestion_threshold": 0.8,
  "voltage_factor": 0.15,
  "voltage_threshold": 0.05,
  "thermal_threshold": 0.2,
  "thermal_cap": 0.3,
  "imbalance_factor": 0.15,
  "zone_factor": 0.15,
  "voltage_drop": "distance"
}
```

`prices` is the name of a file in `config/data/`, the series themselves, or `null`
for the flat `feed_in_tariff` and `utility_price`.
The file's own value: `prices`, whose default is `null`.

## Prices

One price per market step from 00:00: 24 for hourly steps, 96 for quarter-hourly.

```json
{
  "description": "A synthetic day, per kWh in the scenario's money unit, one price per hourly market step from 00:00. utility: time-of-use (off peak at night, a day price, an evening peak); feed_in: flat. Not measured data: a simple shape that makes energy worth more at some hours than at others (decided 26 Oct 2026).",
  "utility": [
    0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2,
    0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3,
    0.4, 0.4, 0.4, 0.4, 0.4,
    0.2, 0.2
  ],
  "feed_in": [
    0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08,
    0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08
  ]
}
```

## Experiment

One JSON object. A file gives what it changes, and every other setting keeps its
default:

```json
{
  "name": "day_end",
  "description": "What the experiment tests",
  "env": "market",
  "scenario": "config/scenarios/validate_market.json",
  "algorithms": ["ppo"],
  "paradigms": ["ctde"],
  "seeds": [0, 1, 2],
  "budget": 240000,
  "eval_points": 10,
  "eval_episodes": 10,
  "results_detail": "standard",
  "trace_days": 3,
  "train_days": {},
  "test_periods": {},
  "env_config": {},
  "variants": {},
  "training": {},
  "model": {},
  "max_parallel": 3,
  "torch_threads": 1,
  "num_env_runners": 0,
  "ray_thread_caps": true,
  "resources": {},
  "test": {}
}
```

### Run

```json
{
  "name": "day_end",
  "description": "How the end of the training episode affects continuous operation (MP-1c, RP-1f): PPO-CTDE on random days or windows of the year, all four arms played on the same uninterrupted test periods. Compare the held-out bill and adjusted_bill. stored_kwh_value: the mean utility price of synthetic_day. The autumn period is for tuning, summer and winter for the results.",
  "env": "market",
  "scenario": "config/scenarios/validate_market.json",
  "algorithms": ["ppo"],
  "paradigms": ["ctde"],
  "seeds": [0, 1, 2],
  "budget": 240000,
  "eval_points": 10,
  "eval_episodes": 10,
  "results_detail": "standard",
  "trace_days": 3
}
```

| Setting | Left out or `null` |
|---|---|
| `name` | The file's name |
| `description` | Empty |
| `eval_points` | No evaluations in between: only at step 0 and the end of the budget. The value shown is the file's own |
| `scenario` | Required for the market |
| `algorithms`, `paradigms`, `seeds`, `budget` | Required |

`trace_days` is only read with `results_detail` `"detailed"`.

### Days

Each period's days are left out of `train_days` when the experiment is read. Inside
a period the batteries and reputations carry from day to day.

```json
{
  "train_days": {
    "from": "2016-01-01",
    "to": "2016-12-31"
  },
  "test_periods": {
    "winter": {
      "from": "2016-01-11",
      "to": "2016-01-24"
    },
    "summer": {
      "from": "2016-07-01",
      "to": "2016-07-14"
    },
    "autumn_validation": {
      "from": "2016-10-03",
      "to": "2016-10-16"
    }
  }
}
```

| Setting | Left out |
|---|---|
| `train_days` | The scenario's `grid.day` alone |
| `test_periods` | No held-out days |

### env_config

The environment's settings. `null`: computed by the environment or its default.

```json
{
  "energy_scale": null,
  "reward_scale": null,
  "episode_days": null,
  "truncate_episode": false,
  "random_start_soc": false,
  "terminal_value": false,
  "stored_kwh_value": 0.2833
}
```

| Setting | `null` |
|---|---|
| `energy_scale` | The largest generation or demand in kWh of any participant in any step of any training day |
| `reward_scale` | `max(p_utility) · energy_scale`, with the highest utility price of the day: the bill for `energy_scale` kWh bought from the DSO at its dearest |
| `episode_days` | 1 |
| `stored_kwh_value` | 0: stored energy is worth nothing, and `adjusted_bill` equals the bill. The value shown is the file's own |

A run computes the two scales once, on its training days, and keeps them: validation,
the held-out days and a restored policy use the training values. `terminal_value`
`true` needs a `stored_kwh_value` other than 0.

### variants

The file is the base case, and a variant is an arm of it: runs are algorithms ×
paradigms × variants × seeds. A variant may give any experiment field except
`name`, `description`, `algorithms`, `paradigms`, `seeds`, `variants`, `max_parallel`,
`resources` and `test`. Inside a section it overwrites only the values it names, and a
list as a whole. `scenario` works the same way, or names another file:

```json
{
  "base": {},
  "big_net": {"model": {"fcnet_hiddens": [768, 768]}},
  "nash": {"scenario": {"market": {"mechanism": "nash_bargaining"}}},
  "graph": {"scenario": {"grid": {"method": "graph"}}},
  "low_lr": {"training": {"ppo": {"lr": 0.0001}}},
  "long": {"budget": 480000}
}
```

A started experiment saves each arm complete, as `experiment_<variant>.json` and
`scenario_<variant>.json` in its folder.

The variants of `day_end.json`:

```json
{
  "daily": {},
  "daily_terminal_value": {
    "env_config": {
      "terminal_value": true
    }
  },
  "one_day_bootstrap": {
    "env_config": {
      "truncate_episode": true,
      "random_start_soc": true
    }
  },
  "windows": {
    "env_config": {
      "episode_days": 7,
      "truncate_episode": true,
      "random_start_soc": true
    }
  }
}
```

### training

```json
{
  "ppo": {
    "lr": 0.0003,
    "gamma": 0.99,
    "grad_clip": 0.5,
    "train_batch_size_per_learner": 2400,
    "minibatch_size": 240,
    "num_epochs": 10,
    "lambda_": 0.95,
    "entropy_coeff": 0.01,
    "clip_param": 0.2,
    "use_kl_loss": true,
    "kl_coeff": 0.0,
    "vf_clip_param": 1000000.0
  }
}
```

The file's own values: `train_batch_size_per_learner` and `minibatch_size`, whose
defaults are 500 and 64. Any other key of RLlib's `training()` may be given too, and
has RLlib's default until it is.

### model

```json
{
  "fcnet_hiddens": [256, 256],
  "fcnet_activation": "tanh",
  "head_fcnet_hiddens": [],
  "head_fcnet_activation": "relu",
  "free_log_std": false,
  "log_std_clip_param": 20.0,
  "vf_share_layers": false,
  "bound_mean": true,
  "log_std_bounds": null,
  "free_log_std_parts": true
}
```

`log_std_bounds`: `null` keeps the log σ in no range. Any other key of RLlib's
`DefaultModelConfig` has RLlib's default.

### Resources

```json
{
  "max_parallel": 3,
  "torch_threads": 1,
  "num_env_runners": 0,
  "ray_thread_caps": true,
  "resources": {
    "cpus": 4,
    "mem_gb": 4,
    "minutes": 120,
    "node": null
  }
}
```

`node`: `null` is any node of the partition.

### test

Changes to the experiment's test version:

```json
{
  "test": {
    "seeds": [0],
    "train_days": 1,
    "test_days": 1,
    "budget": 500,
    "eval_episodes": 1,
    "resources": {"minutes": 15}
  }
}
```

| Setting | Left out |
|---|---|
| `seeds` | The experiment's first seed |
| `train_days`, `test_days` | 1: the first training day and the first test day |
| `budget` | One training batch: the largest `train_batch_size_per_learner` any arm gives, or 100 where none does |
| `eval_episodes` | 1 |
| `resources` | 15 minutes, and the experiment's other resources |

The test version always evaluates only at the end of its budget.
