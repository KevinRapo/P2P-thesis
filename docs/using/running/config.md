# Configuration

> Every setting that can be given, what it does and what it defaults to, checked
> against the code on 1 Nov 2026. Update this page when a setting changes.

Three kinds of file configure a run:

| File | Folder | Says |
|---|---|---|
| [Scenario](#scenario) | [`config/scenarios/`](../../../config/scenarios/validate_market.json) | The world: the network, the participants, the market rules and the DSO |
| [Price file](#price-file) | [`config/data/`](../../../config/data/synthetic_day.json) | The DSO's tariffs per market step |
| [Experiment](#experiment) | [`config/experiments/`](../../../config/experiments/day_end.json) | What is done in that world: days, RL settings, seeds, arms and how the runs are run |

The full examples below hold every setting. A file only needs what it changes: a
setting left out takes the default shown, so the values in the examples are the
defaults, except where a table says a setting is required. `null` means "computed"
or "off", as each table says.

**Misspelt settings.** An experiment refuses an unknown field, and so does its
`env_config`, `resources` and `test`. A scenario **silently drops** an unknown key
(so that older files still load): a misspelt scenario setting does nothing and gives
no error.

**What a started experiment reads.** When an experiment starts, its scenario is copied
under `runs/`: the whole experiment and the base scenario into the experiment's folder,
and each run's own arm into that run's folder (`experiment.json`, `scenario.json`). The
runs read those copies, so changing a scenario file later does not change an experiment
already started. Prices stay as they were given: a price file is read from
`config/data/` when a run starts, so it must be the same on the machine that runs it.

## Scenario

Read by [`core/config/store.py`](../../../core/config/store.py) into the records of
[`core/config/scenario.py`](../../../core/config/scenario.py). `name` defaults to
`"untitled"`.

```json
{
  "name": "example",
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
    "partner_preference": false,
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
    "prices": {"utility": 0.3, "feed_in": 0.08},
    "peer_charge_kwh": 0.0,
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

### grid

| Setting | Values | What it does |
|---|---|---|
| `code` | A SimBench code ([catalogue](../data/networks.md)) | The network |
| `day` | `YYYY-MM-DD` | The day played in the Studio, and by an experiment without `train_days`. Otherwise the environment replaces it at every reset ([Days](#days)) |
| `step_hours` | `1.0` or `0.25` | Hours per market step: 24 or 96 steps a day. A price file must have the same number of prices |
| `background` | `"profiles"`, `"off"` | Whether the network elements no participant owns follow their SimBench profiles, or stay at 0 |
| `v_min_pu`, `v_max_pu` | numbers, `null` | The voltage limits. Outside them the power flow records a violation. They set no fee. `null`: each bus's own limit |
| `line_max_percent` | number, `null` | The line loading limit, recorded the same way. `null`: each line's own limit |
| `method` | `"powerflow"`, `"graph"` | Where the DSO's fees read the line loading from: the AC power flow, or the graph model ([P1] §3.5). The power flow runs and is recorded either way ([grid methods](../../methodology/market/grid-methods.md)) |
| `graph_capacity` | `"paper"`, `"ratings"` | With `"graph"`: the capacity per line. `"paper"` spreads a total over the lines, `C_e = C_total · (1/ℓ_e) / Σ_k (1/ℓ_k)` for lengths `ℓ`; `"ratings"` uses each line's own rating |
| `graph_total_kw` | number, `null` | The total of `"paper"`. `null`: the sum of the line ratings. [P1] gives no value; the original uses 1e6 kW |

### participants

One entry per participant, in the order agents get their index.

| Setting | Values | What it does |
|---|---|---|
| `id` | text, required | The participant's name, and the agent's |
| `bus` | a bus of the network, required | Where it sits on the grid |
| `owns` | list of network elements, `[]` | The loads, generators and storage it takes over: its profiles are theirs |
| `battery` | object, `null` | Its battery. `null`: none |

The battery ([P1] eq. 16):

| Setting | Values | What it does |
|---|---|---|
| `capacity_kwh` | positive, required | Energy capacity |
| `min_soc`, `max_soc` | `0 ≤ min < max ≤ 1` | The usable state-of-charge window |
| `charge_efficiency`, `discharge_efficiency` | in `(0, 1]` | Losses on the way in and out |
| `initial_soc` | inside the window | The charge at the start of a fresh episode |
| `max_power_kw` | positive, **required** | Power limit in kW. Every step is bounded by both the energy the window leaves and this limit over the step. [P1] §3.4 names charge and discharge rates; eq. 16 has none. A SimBench storage unit brings its own; SimBench's ratio is capacity ÷ 2 h |

### market

| Setting | Values | What it does |
|---|---|---|
| `mechanism` | `"average"`, `"buyer"`, `"seller"`, `"bid_ask_spread"`, `"nash_bargaining"`, `"proportional_surplus"` | The price of a matched pair ([`clearing_price.py`](../../../core/market/clearing_price.py), [P1] §3.3.3) |
| `min_price`, `max_price` | numbers | Order prices are limited to this range ([P1] eq. 2) |
| `min_quantity` | kWh | An order at or below this is dropped |
| `max_quantity` | kWh | Orders are cut to this |
| `price_decimals` | integer | Order prices are rounded to this many decimals: 2 is whole cents, so equal prices occur and reputation can break the tie (MP-5d) |
| `reliability_weight`, `fairness_weight`, `grid_weight` | shares adding up to 1 | The reputation's three weights ([P1] eq. 12; the paper gives no values) |
| `reputation_decay` | `0` to `1` | Share of the old reputation kept per hour, applied as `decay ** step_hours` (M-43). 0.8 halves it in about 3.1 hours |

These five apply **only to the market's rule-based participants**, as played in the
Studio. They do not affect an RL agent's orders, whose prices and partners come from
the action:

| Setting | Values | What it does |
|---|---|---|
| `partner_preference` | `true`, `false` | Rule-based participants name a partner ([P1] eq. 2, stage 1 of the clearing) |
| `partner_reputation_weight` | `0` to `1` | How they choose it: 0 the nearest, 1 the most reputable |
| `bid_margin` | below `0.5` | Sellers ask `FiT + margin · spread`, buyers bid `utility − margin · spread`. From 0.5 up, peers no longer overlap |
| `bid_jitter` | number | Random spread around those prices, as a share of the tariff spread |
| `seed` | integer | Seed of the jitter |

The `net_position` baseline of the RL evaluation has its own margin of 0.3 and does
not read `bid_margin`.

### dso

| Setting | Values | What it does |
|---|---|---|
| `prices` | file name, or an object | The one entry for `p_FiT`, what the DSO pays per kWh, and `p_utility`, what it charges per kWh: the name of a [price file](#price-file) without `.json`; flat tariffs, `{"utility": 0.3, "feed_in": 0.08}`; or the series themselves, in the file's format. `feed_in` must stay below `utility`, less `peer_charge_kwh`, at every step |
| `peer_charge_kwh` | non-negative | Grid and tax charge per kWh on a peer trade, paid by the buyer; not in [P1]. Order prices stop at `utility_price − peer_charge_kwh`, so a buyer never pays more than the DSO asks. `0`: the paper's market. What it stands for and the values real regimes give: [Tariffs and the peer charge](../../methodology/market/tariffs.md) (MP-4h) |
| `fees_charged` | `true`, `false` | Whether fees are paid. They are calculated and recorded either way |
| `fee_buyer_share` | `0` to `1` | The buyer's share of a peer trade's fee; the seller pays the rest. A trade with the DSO is paid by the participant |
| `loss_factor` | per km | `κ` of [P1] eq. 18: `l_ij = d_ij · q_ij · κ` |
| `congestion_factor`, `congestion_threshold` | numbers | `f_cong` and `C_threshold` of eq. 8a: above the threshold, the fee is `factor · (c − threshold) · value` |
| `voltage_drop` | `"distance"`, `"measured"` | `V_drop` of eq. 8c: `voltage_factor · d_ij`, or the voltage difference between the two buses in the step's power flow |
| `losses` | `"trades"`, `"bcdla"`, `"pro_rata"` | Who pays the network's losses. `"trades"`: [P1] eq. 18, each trade's loss $\kappa\, d_{ij}\, q_{ij}$ priced into its fee as $F_\text{trans}$. A rule of [losses.py](../../../core/grid/losses.py): the step's measured power-flow losses shared out, each participant paying its share at the step's utility price (a negative share is paid back) and $F_\text{trans}$ 0. `"bcdla"` needs a radial network ([Adding an option](../../methodology/architecture/development/options.md)) |
| `voltage_factor` | per km | `f_volt` of eq. 8f. Only read with `"distance"` |
| `voltage_threshold` | number | `V_threshold` of eq. 8c: the cap on the voltage part |
| `thermal_threshold`, `thermal_cap` | threshold in `[0, 1)` | `T_threshold` and `f_threshold` of eq. 8g and 8d |
| `imbalance_factor` | number | `f_imb` of eq. 8b, on a DSO trade that worsens the balance |
| `zone_factor` | number | `f_zone` of eq. 8e, the bonus for a same-zone trade |

[P1] gives no fee factors. The defaults are the original code's.

## Price file

A JSON file in `config/data/`, one price per market step from 00:00, per kWh in the
scenario's money unit: 24 prices for hourly steps, 96 for quarter-hourly. Time-of-use
tariffs are decided in MP-0b.

A file can also hold every date's own prices under `days`, as
`{"2016-06-01": {"utility": [...], "feed_in": [...]}, ...}`. The market then trades at
the prices of the day it plays, and refuses a day the file does not have; `utility`
and `feed_in` at the top are the mean day. `date_shift` (optional) says that the
prices are from that many days after their key; only the Inspect page reads it, to
show the real dates. `de_2024.json` and `de_2024_flat.json` are such files, from
[`build_de_2024.py`](../../../config/data/build_de_2024.py): German day-ahead prices of
2024 as a dynamic household tariff, with spot-based or flat feed-in (how they are built, and the DESTATIS household price behind them: [Prices](../data/prices.md)). Their keys are
the market's dates of 2016, and each takes the day 2926 days later, the same weekday:
2016-01-01 trades at the prices of 2024-01-05, 2016-12-31 at those of 2025-01-04.

```json
{
  "description": "Free text, not read.",
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

| Setting | Values | What it does |
|---|---|---|
| `utility` | list, required | `p_utility` per step |
| `feed_in` | list, required | `p_FiT` per step |
| `description` | text | Notes for the reader |

The same two series can be given directly as the scenario's `dso.prices`. A list of
the wrong length is refused.

## Experiment

Read by [`core/runner/spec.py`](../../../core/runner/spec.py). Writing an experiment out
in the Studio shows the same settings with the values it runs with.

```json
{
  "name": "example",
  "description": "What the experiment tests",
  "env": "market",
  "scenario": "config/scenarios/validate_market.json",
  "algorithms": ["ppo"],
  "paradigms": ["dtde", "ctde", "ctce"],
  "seeds": [0, 1, 2],
  "budget": 240000,
  "eval_points": null,
  "eval_episodes": 10,
  "train_days": {"from": "2016-01-01", "to": "2016-12-31"},
  "test_periods": {
    "winter": {"from": "2016-01-11", "to": "2016-01-24"},
    "summer": ["2016-07-01", "2016-07-02", "2016-07-03"]
  },
  "env_config": {
    "reward": "bill",
    "grid_capacity_kwh": null,
    "observation": "paper",
    "energy_scale": null,
    "reward_scale": null,
    "tariff_range": null,
    "forecast_error": 0.0,
    "episode_days": null,
    "truncate_episode": false,
    "random_start_soc": false,
    "terminal_value": false,
    "stored_kwh_value": null
  },
  "variants": {
    "base": {},
    "low_lr": {"training": {"ppo": {"lr": 0.0001}}},
    "big_net": {"model": {"fcnet_hiddens": [768, 768]}},
    "nash": {"scenario": {"market": {"mechanism": "nash_bargaining"}}},
    "graph": {"scenario": {"grid": {"method": "graph"}}},
    "long": {"budget": 480000}
  },
  "training": {
    "ppo": {
      "lr": 0.0003,
      "gamma": 0.99,
      "lambda_": 0.95,
      "use_gae": true,
      "use_critic": true,
      "clip_param": 0.2,
      "vf_clip_param": 1000000.0,
      "vf_loss_coeff": 1.0,
      "entropy_coeff": 0.01,
      "use_kl_loss": true,
      "kl_coeff": 0.0,
      "kl_target": 0.01,
      "train_batch_size_per_learner": 500,
      "minibatch_size": 64,
      "num_epochs": 10,
      "shuffle_batch_per_epoch": true,
      "grad_clip": 0.5,
      "grad_clip_by": "global_norm"
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
  "resources": {"cpus": 4, "mem_gb": 4, "minutes": 120, "node": null},
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

### Run

| Setting | Values | What it does |
|---|---|---|
| `name` | a plain folder name | The experiment's folder under `runs/`. Default: the file's name |
| `description` | text | Notes for the reader |
| `env` | `"market"`, or `"module:Class"` | The environment |
| `scenario` | file relative to the repository root, or the scenario itself; required for the market | The world |
| `algorithms` | `["ppo"]`, required | PPO only |
| `paradigms` | any of `"ctce"`, `"ctde"`, `"dtde"`, required | The training paradigms |
| `seeds` | list of distinct integers, required | One run per seed |
| `budget` | positive integer, or `{"ppo": integer}`; required | Environment steps per run |
| `eval_points` | integer, `{"ppo": integer}`, `null` | Evaluations during training, the final one included: 4 on a budget of 24000 evaluate at 6000, 12000, 18000 and 24000. Every run also evaluates at step 0 and at the end. `null`: only those two |
| `eval_episodes` | integer | Episodes per evaluation |

The number of runs is algorithms × paradigms × variants × seeds.

### Days

Four settings decide which days are played, and they are easy to confuse:

| Setting | Where | Says |
|---|---|---|
| `train_days` | experiment | The days training may draw from. Left out: `grid.day` alone |
| `test_periods` | experiment | Named periods of held-out days. Left out: no held-out evaluation |
| `episode_days` | `env_config` | How many consecutive days one training episode plays. Default 1 |
| `grid.day` | scenario | One day, for the Studio and for an experiment without `train_days` |

`train_days` and each period are written as `{"from": ..., "to": ...}` (both days
included) or as a list of dates.

**What happens to them, in order:**

1. **Reading the file.** Every test day is removed from `train_days`. So
   `train_days` can be the whole year, and a period inside it is held out without
   further effort. The order of `test_periods` is kept.
2. **The scales.** The run computes `energy_scale` and `reward_scale` once, from the
   remaining training days, and keeps them for everything below
   ([env_config](#env_config)).
3. **The windows.** The environment lists every run of `episode_days` consecutive
   calendar days that lies wholly inside the training days. A held-out period breaks
   the calendar, so no window crosses it. If no run is long enough, the shorter ones
   are used.
4. **Training.** Each episode draws one window at random, from the run's seed. The
   batteries start at `initial_soc`, or at a random charge with `random_start_soc`,
   and reputations start at 0.5. Inside a window, each day follows the last with the
   batteries and reputations as they were at midnight. An episode lasts `episode_days`
   days: 24 × `episode_days` steps when hourly.
5. **The end of an episode.** By default it **terminates**, and the return stops
   there. With `truncate_episode` it is **truncated**, and the final observation is
   the start of the next calendar day, with the state carried over, for the critic to
   bootstrap from. That next day is not checked against `train_days`, so after the last
   day before a period it can be a test day; it is only ever an observation, and that
   day is never played.
6. **Evaluation during training.** `eval_points` evaluations play `eval_episodes`
   episodes each, drawn the same way, from the training days, on seeds training does
   not use (1,000,000 upwards). The training settings apply. This measures the
   policy on days it may have seen, and is not held out.
7. **Held-out evaluation.** After training, the policy and the baselines play every
   test day once, in order, on seeds 2000, 2001, and so on. The first day of each
   period starts from the scenario's initial state; every later day of the period
   continues from the one before. So a period plays as one uninterrupted stretch,
   whatever `episode_days` was in training. Results are kept per day and participant.

Step 7 uses three options of the environment's `reset`, set by the runner and not by
any file:

| Option | What it does |
|---|---|
| `day` | Plays exactly that day (`one_day` in `MarketEnv`). The environment does not draw, randomise the charge, add the stored-energy reward or move to the next day, so training settings cannot change a test day's rewards |
| `carry` | Starts from the batteries and reputations the last episode left. `true` for every day of a period but the first |
| `period` | The period's name, passed on to the infos so results can be grouped. Changes nothing in the market |

### env_config

The environment's settings, in
[`core/env_defaults.py`](../../../core/env_defaults.py). The runner adds `scenario`,
`days` and `seed` itself, and a file cannot give them.

| Setting | Values | What it does |
|---|---|---|
| `reward` | `"bill"`, `"salazar"` | What the agents learn from ([`reward.py`](../../../core/env/reward.py)). `"bill"`: the net bill over `reward_scale`. `"salazar"`: the original code's reward, not scaled by `reward_scale`. The money is reported either way |
| `grid_capacity_kwh` | positive, `null` | The grid capacity `C` of `"salazar"`, which needs it. SimBench has no single capacity, so a run states one. `"bill"` does not read it |
| `observation` | `"paper"`, `"pruned"` | Which signals the agents see ([The observation vector](../../methodology/environment/observation.md)). `"paper"`: all 42. `"pruned"`: the 22 of `PRUNED_OBS` in [`signals.py`](../../../core/market/signals.py). The partners' reputations follow either way, and the rewards do not depend on this setting |
| `energy_scale` | kWh, `null` | `E`, which scales the energy signals of the observation. `null`: the largest generation or demand of any participant in any step of any training day |
| `reward_scale` | number, `null` | What the reward is divided by. `null`: `max(p_utility) · E`, the bill for `E` kWh bought from the DSO at its dearest |
| `tariff_range` | `[low, high]`, `null` | The lowest feed-in tariff and the highest utility price, which scale the prices of the observation. `null`: from the training days, kept for every later evaluation |
| `forecast_error` | 0 to below 1 | The largest relative error of the forecasts in `remaining_demand` and `remaining_supply`. 0: the true future. Above 0: each later step of the day is forecast as its true value times $(1 + \varepsilon)$, $\varepsilon$ uniform in $[-e, e]$, drawn when the day starts; the market still plays the true profiles. [P2] Table 7 gives 0.3 ([Observation](../../methodology/environment/observation.md)) |
| `episode_days` | integer, `null` | Days per training episode ([Days](#days)). `null`: 1 |
| `truncate_episode` | `true`, `false` | Ends a window with truncation, not termination ([Days](#days), step 5) |
| `random_start_soc` | `true`, `false` | Each window starts with the batteries at a random charge in their window |
| `terminal_value` | `true`, `false` | The window's last reward adds the change of the stored energy at `stored_kwh_value`. Needs a `stored_kwh_value` other than 0 |
| `stored_kwh_value` | money per kWh, `null` | What a stored kWh is worth. `null`: 0. Also sets the reported `adjusted_bill`, with or without `terminal_value` |

A run resolves the two scales once and records them in `run.json`. Evaluation, the
held-out days and a restored policy all use those values, so a reward means the same
everywhere. The scales are one number for all participants. The formulas are in
[`reward.py`](../../../core/env/reward.py) and [`MarketEnv`](../../../core/env/market_env.py).

### variants

The file is the base case, and a variant is an arm of it. It may give any experiment
field except `name`, `description`, `algorithms`, `paradigms`, `seeds`, `variants`,
`max_parallel`, `resources`, `test` and `test_days`. Inside a section it overwrites
only the values it names, and a list as a whole. `scenario` works the same way, or
names another file; its `dso.prices` replaces the base's as a whole. `{}` is the base
case itself. With variants, only the variants run: the base case needs a `{}` of its own.

A started experiment saves each arm complete, as `experiment.json` and `scenario.json`
in the folder of each of its runs.

### training

Passed to RLlib's `AlgorithmConfig.training()`, per algorithm, over the defaults in
[`core/rl_defaults.py`](../../../core/rl_defaults.py). "RLlib" is the value RLlib itself
would use; a blank means the same value is kept.

| Setting | Ours | RLlib | What it does |
|---|---|---|---|
| `lr` | `0.0003` | `5e-5` | Learning rate (RP-6b) |
| `gamma` | `0.99` | | Discount factor |
| `lambda_` | `0.95` | `1.0` | GAE λ |
| `use_gae` | `true` | | Advantages by GAE |
| `use_critic` | `true` | | Use the critic as a baseline. Needed by GAE |
| `clip_param` | `0.2` | `0.3` | PPO's clip on the probability ratio |
| `vf_clip_param` | `1000000.0` | `10.0` | RLlib's cap on the squared value error. Raised so that a large error still gives a gradient |
| `vf_loss_coeff` | `1.0` | | Weight of the value loss |
| `entropy_coeff` | `0.01` | `0.0` | Weight of the entropy bonus |
| `use_kl_loss` | `true` | | Computes the KL between the collecting and updated policy |
| `kl_coeff` | `0.0` | `0.2` | Its weight in the loss. 0: it is only logged (RP-4a) |
| `kl_target` | `0.01` | | Target of RLlib's adaptive coefficient. No effect with `kl_coeff` 0 |
| `train_batch_size_per_learner` | `500` | `4000` | Environment steps collected per update (RP-6b) |
| `minibatch_size` | `64` | `128` | Samples per gradient step (RP-6b) |
| `num_epochs` | `10` | `30` | Passes over each batch (RP-6b) |
| `shuffle_batch_per_epoch` | `true` | | Shuffles the batch before each pass |
| `grad_clip` | `0.5` | `null` | The limit on the gradient |
| `grad_clip_by` | `"global_norm"` | | How it is applied |

Any other key of `training()` may be added and has RLlib's default until it is. A key
`training()` does not know stops the run when it starts. `settings_effective` in
`run.json` records these settings with the values a run used.

### model

The network, the same for every paradigm. `model` overrides RLlib's
`DefaultModelConfig`. The first seven are RLlib's, the last three ours
([`core/rl/modules.py`](../../../core/rl/modules.py)).

| Setting | Ours | RLlib | What it does |
|---|---|---|---|
| `fcnet_hiddens` | `[256, 256]` | | Hidden layers of the actor and of the critic |
| `fcnet_activation` | `"tanh"` | | Their activation |
| `head_fcnet_hiddens` | `[]` | | Extra layers in the policy and value heads |
| `head_fcnet_activation` | `"relu"` | | Their activation |
| `free_log_std` | `false` | | RLlib's state-independent log σ. Use `free_log_std_parts` for the mixed action |
| `log_std_clip_param` | `20.0` | | RLlib's clip on the log σ. Has no effect on a `Dict` or `Tuple` action, so none on the market's |
| `vf_share_layers` | `false` | `true` | Whether actor and critic share layers. Separate here (L-04) |
| `bound_mean` | `true` | ours | Each continuous part's mean through tanh, inside the action's bounds (RP-3h) |
| `log_std_bounds` | `null` | ours | `[low, high]` for the log σ. `null`: no range (RP-3h) |
| `free_log_std_parts` | `true` | ours | One learned log σ per continuous part, the same in every state (RP-3h) |

`DefaultModelConfig` has further keys, for weight initialisers, convolutions and
LSTMs. They are accepted and stay at RLlib's defaults. The modules here are fully
connected, and none of them has been used or tested.

### Resources

| Setting | Values | What it does |
|---|---|---|
| `max_parallel` | integer | Runs at the same time |
| `torch_threads` | integer | Torch threads per run |
| `num_env_runners` | integer | Sampling processes per run. 0: sampling happens in the run's own process |
| `ray_thread_caps` | `true`, `false` | Limits Ray's thread pools to one thread each. `false`: Ray's own sizes, from the node's hardware |
| `resources.cpus`, `resources.mem_gb`, `resources.minutes` | positive numbers | What one run asks of a SLURM cluster |
| `resources.node` | a node's name, `null` | One node by name. `null`: any node of the partition |

`resources` only matters on a SLURM cluster, and a key it does not know is refused.

### test

An experiment's test version is the smallest version of it, to prove that the pipeline
works, not to train. `test` changes that version. It always evaluates only at the
end of its budget.

| Setting | Left out |
|---|---|
| `seeds` | The experiment's first seed |
| `train_days`, `test_days` | 1: the first training day and the first test day |
| `budget` | One training batch: the largest `train_batch_size_per_learner` any arm gives, or 100 where none does |
| `eval_episodes` | 1 |
| `resources` | 15 minutes, and the experiment's other resources |

## Set in the code

Not in any file ([`config.py`](../../../core/rl/config.py)):

| Setting | Value |
|---|---|
| `framework` | `torch` |
| `env_runners.sample_timeout_s` | `None` |
| `learners.num_learners` | `0` |
| `learners.num_gpus_per_learner` | `0` by default |
| `training.learner_class` | `PPOLearner` |
| `reporting.min_time_s_per_iteration` | `0` |
| `debugging.seed` | The run's seed |
| `multi_agent.policies` | One per agent, or one for the group in CTCE |

`normalize_actions` (`True`) and `clip_actions` (`False`) are RLlib's defaults, recorded
in `settings_effective`. They belong to RLlib's `environment()`, so `training` cannot
set them.

This machine's settings are not experiment settings: folders and the cluster's account
are in `.env` ([`.env.example`](../../../.env.example)), and where experiments run is in
[`hpc/targets.toml`](../../../hpc/targets.toml).
