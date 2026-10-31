# Master example

> Every setting that can be defined, in one scenario and one experiment, checked
> against the code on 31 Oct 2026. The values are the defaults, or an example where a
> setting has no default. Update this page when a setting changes.

## Scenario

```json
{
  "name": "master",
  "grid": {
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
  },
  "participants": [
    {
      "id": "P1",
      "bus": "LV1.101 Bus 7",
      "owns": ["LV1.101 Load 9", "LV1.101 SGen 1"],
      "battery": {
        "capacity_kwh": 10.0,
        "min_soc": 0.1,
        "max_soc": 0.9,
        "charge_efficiency": 0.95,
        "discharge_efficiency": 0.95,
        "initial_soc": 0.5,
        "max_power_kw": 5.0
      }
    },
    {
      "id": "P2",
      "bus": "LV1.101 Bus 8",
      "owns": ["LV1.101 Load 2", "LV1.101 SGen 4"],
      "battery": null
    }
  ],
  "market": {
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
  },
  "dso": {
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
}
```

## Price file

`dso.prices` names a file in `config/data/`, here `synthetic_day`:

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

```json
{
  "name": "master",
  "description": "What the experiment tests",
  "env": "market",
  "scenario": "config/scenarios/validate_market.json",
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
    }
  },
  "env_config": {
    "energy_scale": null,
    "reward_scale": null,
    "episode_days": 7,
    "truncate_episode": true,
    "random_start_soc": true,
    "terminal_value": false,
    "stored_kwh_value": 0.2833
  },
  "algorithms": ["ppo"],
  "paradigms": ["dtde", "ctde", "ctce"],
  "seeds": [0, 1, 2],
  "variants": {
    "base": {},
    "low_lr": {
      "training": {
        "ppo": {
          "lr": 0.0001
        }
      }
    },
    "big_net": {
      "model": {
        "fcnet_hiddens": [768, 768]
      }
    },
    "nash": {
      "scenario": {
        "market": {
          "mechanism": "nash_bargaining"
        }
      }
    },
    "daily": {
      "env_config": {
        "episode_days": 1,
        "truncate_episode": false
      },
      "budget": 480000
    }
  },
  "budget": 240000,
  "eval_points": 10,
  "eval_episodes": 10,
  "results_detail": "standard",
  "trace_days": 3,
  "training": {
    "ppo": {
      "lr": 0.0003,
      "gamma": 0.99,
      "grad_clip": 0.5,
      "train_batch_size_per_learner": 500,
      "minibatch_size": 64,
      "num_epochs": 10,
      "lambda_": 0.95,
      "entropy_coeff": 0.01,
      "clip_param": 0.2,
      "use_kl_loss": true,
      "kl_coeff": 0.0,
      "vf_clip_param": 1000000.0
    }
  },
  "model": {
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
  },
  "max_parallel": 3,
  "torch_threads": 1,
  "num_env_runners": 0,
  "ray_thread_caps": true,
  "resources": {
    "cpus": 4,
    "mem_gb": 4,
    "minutes": 120,
    "node": null
  },
  "test": {
    "seeds": [0],
    "train_days": 1,
    "test_days": 1,
    "budget": 500,
    "eval_episodes": 1,
    "resources": {
      "minutes": 15
    }
  }
}
```

In the scenario, `feed_in_tariff` and `utility_price` only apply when `dso.prices` is
`null`. `budget` and `eval_points` may also be given per algorithm, e.g.
`{"ppo": 240000}`.

## RLlib settings

`training` holds every PPO setting the code defines, and `model` every network
setting. Other settings of RLlib's `training()` may be added to `training`.

Set in the code ([`config.py`](../../core/rl/config.py)), not in a file:

| Setting | Value |
|---|---|
| `framework` | `torch` |
| `env_runners.sample_timeout_s` | `None` |
| `learners.num_learners` | `0` |
| `learners.num_gpus_per_learner` | `0` by default |
| `training.learner_class` | `PPOLearner` |
| `reporting.min_time_s_per_iteration` | `0` |
| `debugging.seed` | The run's seed |
| `multi_agent.policies` | One per agent |

Not defined by the code, and kept at RLlib's default. A run records them in
`settings_effective` in `run.json`:

| Setting | Default |
|---|---|
| `use_gae` | `True` |
| `use_critic` | `True` |
| `vf_loss_coeff` | `1.0` |
| `kl_target` | `0.01` |
| `shuffle_batch_per_epoch` | `True` |
| `grad_clip_by` | `global_norm` |
| `normalize_actions` | `True` |
| `clip_actions` | `False` |
