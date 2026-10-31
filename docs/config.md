# Config

> Every configuration file and section, as raw JSON. An overview for now: the
> examples are copies, taken on 31 Oct 2026 from
> [`validate_market.json`](../config/scenarios/validate_market.json),
> [`synthetic_day.json`](../config/data/synthetic_day.json) and
> [`day_end.json`](../config/experiments/day_end.json), with every setting written
> out. The files themselves are what runs read.

A scenario is the world: the network, the participants, the market and the DSO. An
experiment says what is done in it. Price files hold the DSO's tariffs.

| File | Folder | Says |
|---|---|---|
| Scenario | [`config/scenarios/`](../config/scenarios/validate_market.json) | The network, participants, market rules and DSO |
| Prices | [`config/data/`](../config/data/synthetic_day.json) | The DSO's tariffs per market step |
| Experiment | [`config/experiments/`](../config/experiments/day_end.json) | Days, RL settings, seeds, arms and how the runs are run |

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
  "eval_every": 24000,
  "eval_points": 10,
  "eval_episodes": 10,
  "results_detail": "standard",
  "trace_days": 3,
  "train_days": {},
  "test_days": {},
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

`eval_every` and `eval_points` are alternatives: give one of the two.

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
  "eval_every": null,
  "eval_points": 10,
  "eval_episodes": 10,
  "results_detail": "standard",
  "trace_days": 3
}
```

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

Without `test_periods`, `test_days` is a range or a list:

```json
{
  "train_days": {"from": "2016-06-01", "to": "2016-06-30"},
  "test_days": {"from": "2016-07-01", "to": "2016-07-14"}
}
```

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

`grid` and `dso` may also be given here, to replace settings of the scenario:

```json
{
  "env_config": {"grid": {"method": "graph"}}
}
```

### variants

The arms of the experiment. Each gives its own `env_config` or training settings on
top of the experiment's.

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
