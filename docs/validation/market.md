# Market layer: what was wrong and what changed

> Every problem found in the **market layer** of MARLEM: in the original code, in
> the paper [P1], or in the method itself. For each one, what was wrong, where it
> came from, and what `marlem-clean` does about it. The reinforcement-learning layer
> (actions, observations, reward, KPIs, training) is validated separately, starting
> with the training layer in [rl.md](rl.md), and is left out here.

## Scope and sources

**Market layer** means everything that turns orders into trades, money and
energy:

- order validation and the three clearing stages;
- pricing mechanisms;
- the DSO (stage 3, balance, fees);
- transmission losses;
- settlement, the battery and each participant's balance and profit;
- reputation and the trade ledger;
- the grid model as the market uses it.

**Sources.**

- **IDs `I-xx`** are from the validation issue register
  (`docs_thesis/thesis/validation/issues.md` on the refactor branch).
- **The original code** is the authors' MARLEM repository, [salazarna/marlem](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7), at its
  current `main` (commit `15d6715`, March 2026). Every code link and snippet points
  there, pinned to that commit, so the line numbers stay valid.
- **IDs `N-xx`** are new findings made while rebuilding the market in
  `marlem-clean`. They are not in the register.
- **[P1]** is the MARLEM paper (Salazar-Peña et al., Applied Energy 412, 2026);
  its method is summarised in [methodology.md](../marlem/methodology.md).

**Origin** (as in the register):

| Origin | Meaning |
|---|---|
| Paper | The paper itself is wrong, contradictory or silent where the method needs an answer |
| Fidelity | The original code does not do what the paper says |
| Code | A programming defect that the paper has nothing to say about |

**Status in `marlem-clean`:**

| Status | Meaning |
|---|---|
| **Fixed** | Rebuilt to match the paper; the wrong behaviour is gone |
| **Replaced** | The part was replaced by the SimBench network and its AC power flow, so the problem no longer exists |
| **Decided** | The paper is silent or contradictory; a rule was chosen and recorded (see [structure.md, Choices](../structure.md#choices-in-the-rebuilt-market-step)) |
| **Open** | Known, not resolved yet |
| **Flagged** | Kept as in the original on purpose, but worth questioning |

## Summary

| Part of the market | Issues | Fixed | Replaced | Decided | Open | Flagged |
|---|---|---|---|---|---|---|
| [1. The market step](#1-the-market-step) | 4 | 3 | 1 | 0 | 0 | 0 |
| [2. Orders and feasibility](#2-orders-and-feasibility) | 4 | 4 | 0 | 0 | 0 | 0 |
| [3. Clearing stages](#3-clearing-stages) | 3 | 1 | 0 | 2 | 0 | 0 |
| [4. Pricing mechanisms](#4-pricing-mechanisms) | 3 | 2 | 0 | 1 | 0 | 0 |
| [5. Settlement, battery and balances](#5-settlement-battery-and-balances) | 8 | 7 | 0 | 1 | 0 | 0 |
| [6. DSO: balance and grid fees](#6-dso-balance-and-grid-fees) | 11 | 5 | 0 | 3 | 0 | 3 |
| [7. Grid model used by the market](#7-grid-model-used-by-the-market) | 7 | 1 | 5 | 1 | 0 | 0 |
| [8. Reputation](#8-reputation) | 4 | 2 | 0 | 2 | 0 | 0 |
| [9. Trade ledger](#9-trade-ledger) | 1 | 0 | 0 | 0 | 0 | 1 |
| **Total** | **45** | **25** | **6** | **10** | **0** | **4** |

The most consequential ones for any result produced with the original:

- **Batteries ran backwards.** Selling energy *charged* the battery (I-18), and
  the discharge efficiency was applied the wrong way round (I-20).
- **Two pricing mechanisms returned the buyer's bid.** One was `SELLER` (I-13). The
  other was `BID_ASK_SPREAD` (I-17), which the paper's own case study uses.
- **The money and the DSO balance never moved.** Profit was never updated (I-27),
  fees were never charged (I-28), and the DSO balance stayed at 0 (I-24).
- **Reputation only ever measured one thing.** Reliability was always 1 and the
  grid part was always neutral, so only price fairness moved. The decay was weighted
  by the time of day (I-38).
- **The grid's edge flows** started random and piled up over the day (I-33). Only
  stage-1 trades fed them (I-32).

## How to read an issue

Each issue below has the same parts:

- **Header**: ID, title, origin and status in `marlem-clean`.
- **Original code**: the lines at fault, copied from the original repository
  (salazarna/marlem, commit `15d6715`). The caption links to them on GitHub with
  their line numbers. `# ...` stands for lines cut for length, and a few long
  calls are shortened with `...`.
- **Why it is wrong**: what the lines do, which other code calls them or reads
  their result, and how that differs from [P1]. Where a definition looks harmless
  on its own, this part shows the call site that makes it wrong.
- **In `marlem-clean`**: what the rebuild does, with a link, and the new code
  when it is short enough to compare.

<mark class="ok">Fixed</mark>        green: fixed, and you're fine with what was done
<mark class="review">Review</mark>   yellow: the AI fixed it, but you want to look again
<mark class="open">Open</mark>       red: still open


## 1. The market step

### I-01: only 23 of 24 periods run

**Fidelity · Fixed**

[`src/environment/lem.py` L433-L445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L433-L445)

```python
# STEP 4. Update environment state
self.current_step += 1
# ...
# STEP 5. Check if episode is done
if self.current_step >= self.max_steps - 1:
    terminateds = {agent_id: True for agent_id in self.agents_id}
```

**Why it is wrong.** The counter is raised *before* the check, and the check is
against $\text{max_steps} - 1$. With $\text{max_steps} = 24$, the step that played period 22
raises the counter to 23, and $23 \ge 23$ ends the episode. Periods 0-22 run, and
period 23 (the last hour of the day) never does (T1). Every episode loses its last
hour of demand and generation.

**In `marlem-clean`.** A day is $24 / \text{step_hours}$ steps, and `done` is true only
after all of them are recorded ([lem.py](../../core/market/lem.py#L252-L259)).

### I-78: an invalid order stops the simulation

**Fidelity · Fixed**

<mark class="review">Review</mark> This raises a bigger topic, how to deal with invalid actions across all the features

[`src/environment/lem.py` L336-L343](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L336-L343)

```python
for id in self.agents_id:
    action = action_dict[id]
    action_dict[id] = self._agents[id].adjust_action_for_battery(...)

    if not self.action_handler.is_valid_action(id, action_dict[id]):
        raise ValueError(f"Invalid action for {id}: {action_dict[id]}")
```

**Why it is wrong.** [P1] Algorithm 1 keeps an order only `if ValidateOrder(o_i,
S_t)`: an invalid order is dropped, and the market goes on. Here one bad action
raises an exception, which ends the whole episode.

**In `marlem-clean`.** `_validate` clips the price to the market bounds and the
quantity to eq. 15, drops what is left at or below $q_{\min}$, and records each change
as a note ([lem.py](../../core/market/lem.py#L454)).

### I-56: units and time step are mixed

**Paper · Fixed**

[`src/market/matching.py` L33-L36](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L33-L36),
[`src/agent/der.py` L35](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L35),
[`src/agent/battery.py` L99, L117, L135, L162](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L95-L162)

```python
# MarketConfig
min_price: float = 0.0  # Minimum allowed price ($/Wh)
max_price: float = 1000.0  #  Maximum allowed price($/Wh)
min_quantity: float = 0.0  # Minimum allowed quantity (Wh)
max_quantity: float = 1000.0  # Maximum allowed quantity (Wh)

# DERAgent docstring
capacity: Maximum capacity of the DER (W)

# Battery docstrings
energy: Charging energy in kWh        # _can_charge
energy: Discharge energy in kWh       # _can_discharge
energy: Charging energy in Wh         # charge
energy: Discharging energy in Wh      # discharge
```

**Why it is wrong.** The market's own configuration says prices are in \$/Wh
and quantities in Wh. The battery's methods say kWh for the checks and Wh for the
actual charging, and the DER capacity is in W. [P1]'s case study prices in \$/MWh
(35-280), and [P2] plots prices in "\$/kWh". There is no step length anywhere, so
"quantity" means energy per 1-hour step only by convention. Between the comments,
the code and the two papers, a price differs by up to a factor of a million (\$/Wh
vs \$/MWh), and any number that mixes energy, power and price is ambiguous.

**In `marlem-clean`.** Energy is kWh per step, power is kW, prices are per kWh,
and the step length is explicit: `GridSetup.step_hours`, 1 h or 15 min
([scenario.py](../../core/config/scenario.py#L33)). Power becomes energy with
$\text{kW} \cdot \text{step_hours}$ ([der.py](../../core/market/agent/der.py#L59)).

### I-05, I-06: a reset cannot be told which profiles to use

**Code / Fidelity · Replaced**

[`src/environment/lem.py` L281-L293](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L293)

```python
for agent in self._agents.values():
    reputation = self.reputation_handler.reset(seed)
    generation, demand = self.der_profile_handler.reset(agent.capacity,
                                                        self.max_steps)
    agent.reset(reputation, generation, demand, seed)
```

[`src/profile/base.py` L40-L43](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/base.py#L40-L43),
[`src/profile/der.py` L119-L129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L119-L129)

```python
df = pd.read_csv(path)
selected_col = np.random.choice(df.columns)       # a random column
return df[selected_col].tolist()

base_profile = self._load_profile(self.generation_file_path)
scale_factor = np.random.uniform(1.0, 1.3)        # and a random scale
# ...
    varied_value = value * scale_factor * (1 + noise)
```

[`src/profile/der.py` L187-L198](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/profile/der.py#L187-L198)

```python
base_value = effective_max_value * np.exp(-normalized_hour**2)
cloud_noise = np.random.uniform(-0.2 * cloudiness, 0.2 * cloudiness)
noise = np.random.uniform(-noise_magnitude, noise_magnitude)
value = max(0.0, (base_value + noise + cloud_noise) * capacity)
```

**Why it is wrong.** The reset has no way to say *which* profiles an episode
should use, so the market cannot be put back into a defined starting state at all:

- **Profiles given to an agent are thrown away (I-05).** `DERAgent(...)` takes
  generation and demand profiles, but `reset()` always replaces them with the
  profile handler's (T11). `reset()` itself takes no day or profile argument. There
  is no supported way to run the market on a chosen day, or to run the same day
  again.
- **What the handler produces is not a choice of day (I-06).** A CSV profile is a
  random column of the file at a random 1.0-1.3 scale. Depending on what the
  columns hold, that is either a different household for the same agent, or a
  different day with an invented scale; the code does not say which.
- **With a seed, nothing varies; without one, nothing is reproducible.** The reset
  reseeds the global random generator with the configured seed whenever no seed is
  passed (I-03). With a seed set, as in [P2] (seed 42), every episode draws the
  *same* profiles. Without one, no two runs can be compared. Neither is a defined
  rule.
- **The procedural profile is not eq. 17.** [P1] eq. 17 is multiplicative,
  $G = C \cdot I \cdot (1 + \varepsilon_{\text{noise}} + \varepsilon_{\text{cloud}})$.
  The code adds the noise to the irradiance shape instead,
  $(I + \varepsilon_{\text{noise}} + \varepsilon_{\text{cloud}}) \cdot C$, so the
  noise does not scale with the sun and appears at full size at dawn and dusk.

The market needs a reset with a clear rule: the same scenario and day give the
same profiles, and an agent stays the same agent (same elements, same load type)
whatever day is played. The original offers no such reset.

> **Outside the market layer.** Whether profiles *should* differ between episodes
> is a reinforcement-learning question, not a market one. For training, playing a
> different day each episode (e.g. sampled from a year of data, with held-out days
> for evaluation) is desirable, so that agents generalise instead of memorising
> one day. That needs exactly the controllable reset the original lacks: the RL
> layer chooses the day, the market builds it. Under [P2]'s fixed seed, the
> original instead trains on the same profiles in every episode.

**In `marlem-clean`.** Generation and demand come from the SimBench profiles of the
network elements a participant owns, for the scenario's day (`GridSetup.day`), and
`reset()` rebuilds exactly that day every time
([der.py](../../core/market/agent/der.py#L59-L86)). Eq. 17 is not used. Choosing a
different day per episode is not built yet: the grid contract already provides for
it (`GridModel.reset(episode_seed, day)`,
[contract.py](../../core/grid/contract.py)), but `LocalEnergyMarket.reset()` does
not take a day yet. That is for the RL layer to call.

## 2. Orders and feasibility

### I-08: feasibility clipping is not eq. 15

**Fidelity · Fixed**

[`src/agent/der.py` L184-L228](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L184-L228)

```python
price, quantity, is_buy, preferred_partner = action
# ...
if is_buy:
    # Calculate how much energy we need to buy after using our own generation
    energy_deficit = quantity - current_generation
    # ...
    quantity = max(0.0, energy_deficit)
else:
    # Calculate how much energy we can export after using our own generation
    energy_surplus = quantity - current_demand
    # ...
    quantity = max(0.0, energy_surplus)
```

**Why it is wrong.** [P1] eq. 15 bounds an order by the agent's physical position:

- $q_{\text{sell,max}} = \max(0, G - D) + E_{\text{dischargeable}}$
- $q_{\text{buy,max}} = \max(0, D - G) + E_{\text{chargeable}}$

The code instead treats the *requested* quantity as if it were the agent's demand
(buying) or generation (selling) and subtracts the other side from it. A buyer with
$G = 0,\ D = 5$ that asks for 2 kWh is not limited to 5 + its battery room: its
"deficit" is $2 - 0$, and its battery may then cover that, so the order shrinks to
0. A seller with $G = 10,\ D = 1$ asking to sell 3 kWh gets $3 - 1 = 2$. The limit
has nothing to do with what the agent can actually deliver or take.

**In `marlem-clean`.** Eq. 15a-b, with the battery's room from eq. 15c-d
([der.py](../../core/market/agent/der.py#L154-L161)):

```python
def max_sell_kwh(self, step: int) -> float:
    """Eq. 15a: q_sell,max = max(0, G_t − D_t) + E_dischargeable."""
    return max(0.0, self.net_kwh(step)) + self.battery_room()[1]
```

### I-09: an order can be sized as a buy and submitted as a sell

**Fidelity · Fixed by design**

[`src/agent/der.py` L196](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L196),
[`src/environment/lem.py` L358](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L358)

```python
# DERAgent.adjust_action_for_battery: sizing the order
if is_buy:
    energy_deficit = quantity - current_generation
    # ...

# LocalEnergyMarket.step: submitting it
is_buy = bool(is_buy > 0.5)
```

**Why it is wrong.** The action's direction is a continuous number. The sizing
code reads it as *truthy* (any non-zero value is a buy); the submitting code reads
it as `> 0.5`. A raw value of 0.3 is sized with the buy logic, then submitted as a
sell order (T8): the quantity was computed for the wrong side of the market.

**In `marlem-clean`.** The side is a boolean in `OrderIntent`, set once. Turning a
continuous action into a side is RL-layer work.

### I-11: no way to submit nothing

**Paper · Fixed at the market layer**

[`src/agent/der.py` L231-L232](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L231-L232)

```python
price = max(market_config.min_price, min(market_config.max_price, price))
quantity = max(market_config.min_quantity, min(market_config.max_quantity, quantity))
```

**Why it is wrong.** After clipping for the battery the quantity can be 0, but it
is then raised to `min_quantity`. With $q_{\min} > 0$, an agent that has nothing to
trade still submits an order of $q_{\min}$. [P1] eq. 2 has no "no order" action
either.

**In `marlem-clean`.** A participant with nothing to trade places no order, and
`_validate` drops orders at or below $q_{\min}$. Whether an RL action can express
"nothing" is left to the RL layer.

### I-12: clearing overwrites the submitted orders

**Code · Fixed**

[`src/market/matching.py` L347-L348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347-L348),
[`src/market/dso.py` L232, L253](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L212-L253)

```python
# Stage 2
buy_order.quantity -= (proposed_quantity - transmission_loss)
sell_order.quantity -= proposed_quantity

# Stage 3 (DSO), for every remaining order
sell_order.quantity = 0
buy_order.quantity = 0
```

[`src/environment/lem.py` L424-L425](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L424-L425),
[`src/environment/reward.py` L406](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L406)

```python
rewards = {id: self.reward_handler.calculate_reward(agent, orders[id], ...)
# ...
execution_ratio = executed_quantity / order.quantity if order.quantity > 0 else 0
```

**Why it is wrong.** The clearing stages subtract matched quantities from the
order objects themselves, and the DSO sets every remaining one to 0. After
clearing, every order in `orders` has quantity 0. Everything that reads the orders
afterwards (the reward, the KPIs, the info dictionary) sees 0 instead of what was
submitted (T3). The reward's `order.quantity > 0` guard then makes every execution
ratio 0. This is the root cause of the RL layer's I-43.

**In `marlem-clean`.** Every stage works on copies, `work = [replace(o) for o in
orders]`, and returns the remaining orders separately; the submitted orders are
never changed ([clearing.py](../../core/market/clearing.py#L113)).

## 3. Clearing stages

### I-15: DSO-preferred orders are cleared before the peer market

**Paper · Decided**

[`src/market/matching.py` L608-L623](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L608-L623)

```python
# STAGE 1: Handle DSO preferences first
dso_preferred_orders = [o for o in orders if o.partner_id == self.dso.id]
# ...
if dso_preferred_orders:
    dso_trades, _ = self.dso.clear_unmatched_orders(current_step,
                                                    dso_preferred_buys,
                                                    dso_preferred_sells)
    preference_trades.extend(dso_trades)
```

**Why it is wrong.** [P1] §3.3.2 has three stages: mutual preferences, the double
auction, then the DSO for the residual. The code adds a sub-stage the paper does
not have: an order naming the DSO is cleared with the DSO first, before any peer
matching. The paper gives no reason for naming the DSO at all, since its prices
are the worst in the market.

**In `marlem-clean`.** Orders that prefer the DSO skip stages 1 and 2 and are
cleared in stage 3 with the rest
([clearing.py](../../core/market/clearing.py#L118), [L144](../../core/market/clearing.py#L144)).

### I-77: partner choice is a sort and a random pick, not a weighted score

**Fidelity · Fixed**

<mark class="review">Review</mark> How to weight the formula, 50/50 ok?

[`src/agent/der.py` L154-L159](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L154-L159),
[`src/environment/lem.py` L362-L365](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L362-L365)

```python
candidates = [agent for agent in candidates if agent.id != self.id]
candidates.sort(key=lambda x: (-x.reputation, self.location.distance_to(x.location, graph)))
return np.random.choice(candidates[:max(1, len(candidates) // 2 + 1)]).id if randomize else candidates[0].id

# called from step() with:
preferred_partner = self._agents[id].select_preferred_partner([...], graph, randomize=True)
```

**Why it is wrong.** [P1] §3.4: the rule-based strategy "prioritizes partners
based on a weighted score of high reputation and short grid distance". The code
does three other things:

- it sorts by reputation first and uses distance only to break exact ties;
- it picks at random from the top half;
- its candidates include agents on the *same* side of the market, so a seller can
  name another seller, a preference stage 1 can never match.

**In `marlem-clean`.** A weighted score of reputation and closeness, over
participants on the other side of the market only. Both are rescaled over the
candidates, 1 for the best and 0 for the worst, so the weight $w$
(`partner_reputation_weight`, 0.5) gives each the same say:

$$
\text{score}_j = w\, \frac{r_j - r_{\min}}{r_{\max} - r_{\min}}
+ (1 - w)\, \frac{d_{\max} - d_j}{d_{\max} - d_{\min}}
$$

Without the rescaling, reputations that all start at 0.5 and drift by a few
hundredths would lose to distance every time. Ties go to the nearer candidate
([der.py](../../core/market/agent/der.py#L187-L223),
[lem.py](../../core/market/lem.py#L425)).

### I-55: the stage-2 capacity check can never trigger

**Code · Decided**

[`src/market/matching.py` L158, L299-L307](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L158)

```python
self.grid_capacity: float = config.max_quantity * self.num_agents
# ...
if abs(grid_balance) > self.grid_capacity:
    # Grid is already at capacity, skip this match
    if grid_balance > 0:
        sell_idx += 1
    else:
        buy_idx += 1
    continue
```

**Why it is wrong.** "Grid capacity" here is $\text{max_quantity} \cdot N$ (1000 kWh per
agent by default), not anything about the grid. It is compared with the *current*
balance, not with the balance after the trade, and that balance is the DSO
balance, which stays 0 (I-24). The check never fires, so stage 2 has no grid
constraint at all.

**In `marlem-clean`.** The check is gone. [P1] says violating trades "can be
penalized or disallowed by the DSO" without choosing. **Decided: penalized.** The
congestion and thermal fees (eq. 8a, 8d) price the loading of the lines on a
trade's path in the previous power flow, trades with the DSO included (I-54). The
power flow reports voltage and loading violations but blocks no trade.
Disallowing would need a grid check per trade, for example with sensitivity
factors as in Guerrero, Chapman and Verbič (2019), and a rollback: future work.
The episode runs show whether violations occur at all.

## 4. Pricing mechanisms

### I-13: `SELLER` pricing returns the buyer's price

**Fidelity · Fixed**

[`src/market/mechanism.py` L72-L84](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L69-L84),
[`src/market/matching.py` L310-L312](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L310-L312)

```python
class SellerPricing(BasePricing):
    def calculate_price(self,
                        sell_order: Order,
                        *args,
                        **kwargs) -> float:
        return sell_order.price

# the only caller, for every mechanism
trade_price = self.config.price_mechanism.get_instance().calculate_price(buy_order,
                                                                         sell_order,
                                                                         market_price)
```

**Why it is wrong.** The definition looks right on its own: it returns
`sell_order.price`. But the caller passes the arguments **by position**, buy order
first. The parameter named `sell_order` receives the *buy* order, and the real sell
order disappears into `*args`. `SELLER` therefore returns the buyer's bid: buy 200,
sell 50 gives 200 (T6). It behaves exactly like `BUYER`.

**In `marlem-clean`.** Every mechanism has one fixed signature, `(buy_order,
sell_order, reference_price)`, so an argument can no longer land in the wrong
parameter ([clearing_price.py](../../core/market/clearing_price.py#L58-L64)).

### I-17: `BID_ASK_SPREAD` returns the buyer's price too

**Fidelity · Fixed**

[`src/market/mechanism.py` L90-L111](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/mechanism.py#L87-L111)

```python
def calculate_price(self,
                    buy_order: Order,
                    sell_order: Order,
                    factor: float = 0.5,
                    *args,
                    **kwargs) -> float:
    bid_ask_spread = buy_order.price - sell_order.price
    return sell_order.price + bid_ask_spread * max(0.0, min(factor, 1.0))
```

**Why it is wrong.** The same positional call as above passes `market_price` as
the third argument, which here is `factor`. The factor is meant to be 0-1 (0.5 =
midpoint), but it receives a price. With prices in \$/MWh, as in [P1]'s case study
(35-280), any market price above 1 is clipped to 1, and the trade price is the
buyer's bid: buy 200, sell 50, market 100 gives 200 (T12). With prices below 1 the
trade price lands at a meaningless point of the spread. This is the mechanism
[P1]'s Case 5 uses, and §3.3.3 does not define it.

**In `marlem-clean`.** `factor` is a constructor argument (default 0.5), not a
call argument ([clearing_price.py](../../core/market/clearing_price.py#L67-L79)):

```python
def __init__(self, factor: float = 0.5) -> None:
    self.factor = max(0.0, min(factor, 1.0))
```

### I-16: the clearing price includes the DSO's trades

**Paper · Decided**

[`src/market/matching.py` L368-L371, L385](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L368-L385)

```python
# Update totals with DSO trades
for trade in dso_trades:
    total_volume += trade.quantity
    total_value += trade.quantity * trade.price
# ...
clearing_price = total_value / total_volume if total_volume > 0 else self.dso.get_market_price(current_step)
```

**Why it is wrong.** The step's "clearing price" is a volume-weighted average over
*all* trades, including the DSO's at its feed-in tariff and utility price. When
most energy goes to the DSO, the clearing price is mostly the DSO's tariffs. It is
then used as the market signal everywhere: observations, the reputation's
fairness (I-38), and the reference price of the proportional mechanism (eq. 11).
[P1] does not define the clearing price.

**In `marlem-clean`.** Volume-weighted price of the peer trades only, and the
previous price when there were none ([lem.py](../../core/market/lem.py#L513)).

## 5. Settlement, battery and balances

### I-18: selling charges the battery

**Fidelity · Fixed**

[`src/agent/der.py` L294-L305](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L293-L305)

```python
current_generation = self.generation_profile[step]
current_demand = self.demand_profile[step]
net_trade_energy = energy_sold - energy_bought

energy_balance = current_generation - current_demand + net_trade_energy

if energy_balance > 0:
    # Surplus energy - charge battery
    self.battery.charge(energy_balance)
elif energy_balance < 0:
    # Energy deficit - discharge battery
    self.battery.discharge(abs(energy_balance))
```

**Why it is wrong.** Energy *sold* leaves the household, so it must reduce what is
left for the battery; energy *bought* adds to it. [P1] eq. 13 is
$B = (G - D) + (E_{\text{bought}} - E_{\text{sold}})$. The code has the trade term the other way
round, $(G - D) + (\text{sold} - \text{bought})$.

This is not the paper's logic with every sign reversed, which would still give the
right battery behaviour. The one expression mixes two conventions: $G - D$ counts a
surplus as positive, while $\text{sold} - \text{bought}$ counts *exports* as positive.
A consistently mirrored version would need $D - G$ as well, and would charge the
battery when the result is negative; the code charges it when the result is
positive. The inputs are what their names say: `energy_sold` is the energy the agent
sold ([lem.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L401)), so no other sign makes up for it.

The original code itself, run on five households (battery at 50 kWh,
efficiencies 1):

| Household | Left for the battery, eq. 13 | The code's balance | Battery after |
|---|---|---|---|
| $G = D$, sells 10 kWh | −10 | +10 | **60**, charged |
| Surplus 5, sells its surplus | 0 | +10 | **60**, charged |
| Deficit 5, buys its deficit | 0 | −10 | **40**, drained |
| Surplus 5, no trade | +5 | +5 | 55 |
| Deficit 5, no trade | −5 | −5 | 45 |

The code agrees with the paper only when the agent does not trade. As soon as it
trades, the trade term doubles the surplus or deficit instead of cancelling it: a
household that sells its 5 kWh surplus still charges 10 kWh into its battery, and
one that buys its deficit still drains 10 kWh from it (T7). Every result involving
batteries is affected.

**In `marlem-clean`.** Eq. 13, then the battery
([der.py](../../core/market/agent/der.py#L214-L219)):

```python
balance = (g - d) + (bought - sold)  # [P1] eq. 13
charge = b.charge(balance) if b and balance > 0 else 0.0
discharge = b.discharge(-balance) if b and balance < 0 else 0.0
```

### I-19: a charge that would fill the battery is refused entirely

**Fidelity · Fixed**

[`src/agent/battery.py` L104-L111, L140-L156](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L95-L156)

```python
def _can_charge(self, energy: float) -> bool:
    if energy <= 0:
        return False
    # Check if battery is already full
    if self.energy_level + energy >= self.max_soc * self.nominal_capacity:
        return False
    return True

def charge(self, energy: float) -> float:
    if self._can_charge(energy):
        max_energy = min(energy, self.max_soc * self.nominal_capacity - self.energy_level)
        # ...
    else:
        self.state = BatteryState.IDLE
        return 0.0
```

**Why it is wrong.** `charge` already caps the energy at what fits
(`min(energy, room)`), but `_can_charge` refuses any charge that *would* reach
$SoC_{\max}$, so that cap is never used. A battery with 1 kWh of room offered 1.5 kWh
takes nothing. [P1] eq. 16 is $\min(E + E_{\text{in}} \cdot \eta,\ SoC_{\max} \cdot C)$: it fills to the
limit. `_can_discharge` has the same problem at $SoC_{\min}$.

**In `marlem-clean`.** The battery takes what it can and returns how much
([battery.py](../../core/market/agent/battery.py#L121-L128)).

### I-20: discharge efficiency is applied the wrong way

**Fidelity · Fixed**

[`src/agent/battery.py` L167-L179](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L158-L179)

```python
if self._can_discharge(energy):
    max_energy = min(energy, self.energy_level - self.min_soc * self.nominal_capacity)
    energy_discharged = max_energy * self.discharge_efficiency

    self.energy_level -= energy_discharged
    # ...
    return energy_discharged
```

**Why it is wrong.** [P1] eq. 16: delivering $E_{\text{out}}$ drains $E_{\text{out}} / \eta_{\text{discharge}}$
from storage, *more* than is delivered. The code drains $E_{\text{out}} \cdot \eta$, *less* than is
delivered: at $\eta = 0.95$, delivering 10 kWh removes only 9.5 kWh from the battery.
The battery creates energy on every discharge.

**In `marlem-clean`.** $E \leftarrow E - E_{\text{out}} / \eta_{\text{discharge}}$
([battery.py](../../core/market/agent/battery.py#L130-L137)):

```python
given = min(max(0.0, kwh), self.dischargeable_kwh)
self.energy_kwh = max(self.min_kwh, self.energy_kwh - given / self.discharge_efficiency)
```

### I-71: no power limit, and eq. 15 ignores efficiency

**Paper · Decided**

[`src/agent/battery.py` L205-L214](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/battery.py#L205-L214)

```python
def estimate_available_energy(self) -> Tuple[float, float]:
    available_charge = self.max_soc * self.nominal_capacity - self.energy_level
    available_discharge = self.energy_level - self.min_soc * self.nominal_capacity
    return (available_charge, available_discharge)
```

**Why it is wrong.** This is [P1] eq. 15c-d as printed, and the paper is the
problem. It counts room in *stored* energy, but orders are in energy at the bus:
with $\eta_{\text{charge}} = 0.95$ the battery can take $\text{room} / 0.95$ from the bus, and give only
$\text{room} \cdot 0.95$ to it. [P1] §3.4 also says operations are bound by "maximum
charge/discharge rates", but eq. 16 has no rate, and neither does the code.

**In `marlem-clean`.** The room is seen from the bus, $(E_{\max} - E) / \eta_{\text{charge}}$
and $(E - E_{\min}) \cdot \eta_{\text{discharge}}$, and an optional `max_power_kw` caps both
([battery.py](../../core/market/agent/battery.py#L107-L119)).

The power limit comes from SimBench. A participant that takes over a SimBench
storage unit gets it as its battery, with its energy capacity and power rating.
Storage exists only in SimBench's future scenarios (`--1-`, `--2-`); scenario 0 has
none. A battery added anywhere else gets SimBench's ratio, capacity ÷ 2 h, which
holds for all 84 storage units of the twelve LV future-scenario networks.
`BATTERY_PRESETS` offers their 10th, 50th and 90th percentile sizes: 6.8, 13.7 and
66.4 kWh ([placement.py](../../core/config/placement.py#L22-L56)). A
`BatterySetup` written by hand has no limit unless `max_power_kw` is given.

<mark class="review">Review</mark> Can simbench provide the battery power value also or we should provide it ourselves?

### I-22: no household energy balance

**Paper · Fixed**

[`src/environment/lem.py` L392-L411](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L392-L411)

```python
for id in self.agents_id:
    # ... energy_bought, energy_sold from the trades
    self._agents[id].update_energy_tracking(self.current_step, energy_bought, energy_sold)
    self._agents[id].update_battery_from_trades(self.current_step, energy_bought, energy_sold)
```

**Why it is wrong.** After the trades, each household's energy is never closed:
$G - D + \text{bought} - \text{sold}$ goes to the battery (with the wrong sign, I-18), and
whatever the battery refuses (I-19) or cannot hold simply disappears. Nothing says
where it went, and nothing checks that the energy adds up. [P1] gives eq. 13 but
no conservation rule.

**In `marlem-clean`.** Eq. 13 → battery → the rest is exchanged with the upstream
grid untraded and recorded as `external_kwh`. The power flow uses this physical
outcome, never the trades ([der.py](../../core/market/agent/der.py#L196-L247)).
The notebook checks it every step ("nothing left untraded").

### I-26: the agent's "balance" is its net trade, in the other sign convention

**Fidelity, inconsistency · Fixed**

[`src/environment/lem.py` L440](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L440),
[`src/market/matching.py` L435-L445](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L426-L445)

```python
agent.balance = self.market.get_agent_position(id)

def get_agent_position(self, agent_id: str) -> float:
    position = 0.0
    # ...
        if trade.seller_id == agent_id:
            position += trade.quantity  # Positive when selling
        if trade.buyer_id == agent_id:
            position -= trade.quantity  # Negative when buying
    return position
```

**What is going on.** [P1] eq. 13 defines the balance as
$B = (G - D) + (E_{\text{bought}} - E_{\text{sold}})$: positive means surplus. The code's
`agent.balance` is a different quantity under the same name: only the agent's trades,
$\text{sold} - \text{bought}$, with no $G - D$, and positive when the agent is a net
*seller*. An agent that bought exactly its deficit has $B = 0$ in the paper but a
negative "balance" here.

The sign on its own is not a fault. Its only reader in the original code is the
reward's impact term,
`prev_balance = self.dso.balance - agent.balance`
([reward.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/reward.py#L297)), where the DSO balance counts excess
supply as positive. Selling adds supply, so subtracting the agent's net selling
correctly gives the market without this agent. The convention is used
consistently there.

It is an **inconsistency**, not a fault:

- **The name says eq. 13, the content is something else.** The paper's balance is a
  household's energy left after trading; this is its net trade only.
- **The sign convention differs from the rest of the market code.** Everywhere else
  a positive balance means surplus (eq. 13, eq. 20, the DSO balance, the
  reputation, the fees); here positive means "sold more than bought".
- **Its one reader sees it a step late.** `agent.balance` is set after the rewards
  are computed ([lem.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L440)), so the reward uses the
  previous step's value. In the first step it is the random start
  $U(-C, C)$ that `reset()` puts there ([der.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L108)).

**In `marlem-clean`.** `balance_kwh` is eq. 13 ([der.py](../../core/market/agent/der.py#L214)).

### I-27: profit is never updated

**Fidelity · Fixed**

[`src/agent/der.py` L61, L109](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L61),
[`src/environment/observation.py` L342](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L342)

```python
# DERAgent.__init__ and DERAgent.reset: the only two assignments
self.profit: float = 0.0
self.profit = 0.0

# ObservationHandler: read every step
agent.profit,
```

**Why it is wrong.** [P1] eq. 14 is
$\text{profit}_{t+1} = \text{profit}_t + \sum (p_{\text{sell}} q_{\text{sell}} - p_{\text{buy}} q_{\text{buy}})$. In the whole
original code base, the agent's `profit` is assigned only twice, both times 0.
Nothing adds the trades to it. The observation reports it every step, and it is
always 0 (T5). (The DSO's profit, by contrast, is updated.)

**In `marlem-clean`.** `settle` adds each step's revenue minus cost minus grid
fees ([der.py](../../core/market/agent/der.py#L196-L219)). The participants' and
the DSO's money adds up to 0 every step (notebook check "money adds up").

### I-21: demand satisfied ignores battery discharge

**Code · Fixed**

<mark class="review">Review</mark> does salazar say anything about this in their paper? If the trades could always be settled with the DSO then Im not sure why he even included it?

[`src/agent/der.py` L254-L259](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/agent/der.py#L250-L262)

```python
# Demand can be satisfied by: own generation + market purchases + battery discharge
energy_available_for_demand = current_generation + energy_bought

demand_satisfied_this_step = min(current_demand, energy_available_for_demand)
demand_deferred_this_step = max(0.0, current_demand - demand_satisfied_this_step)
```

**Why it is wrong.** The comment lists battery discharge, the code leaves it out.
An agent that covers its night demand from its battery is counted as having
*deferred* that demand. Also, `update_energy_tracking` runs before
`update_battery_from_trades` (lem.py L416-L423), so the discharge is not even known
yet when this runs.

**In `marlem-clean`.** [P1] §3.4.1 tracks "the total demand satisfied versus the
demand deferred, providing a measure of the agent's energy security", and [P1]
and [P2] list the cumulative values among the observations. Every participant's
outcome now has its demand and supply satisfied and deferred
([der.py](../../core/market/agent/der.py#L60-L82)). Generation, purchases and
battery discharge all count, and the battery has settled before they are read.

Since the DSO clears every order, no demand goes physically unmet. *Deferred* is
what the participant's own orders and battery left uncovered, exchanged with the
upstream grid untraded (`external_kwh`). It is a signal of how well an agent
ordered, not a market rule: the reward's unmet-demand penalty $\gamma_{UD}$ is
about the same quantity. With the rule-based bidding it is always 0 (notebook
checks "nothing left untraded" and "satisfied + deferred = demand").

## 6. DSO: balance and grid fees

### I-24: the DSO balance stays at 0

**Fidelity · Fixed**

[`src/market/matching.py` L259-L266, L338-L344, L374](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L258-L374)

```python
# after stage 1
for trade in preference_trades:
    if trade.buyer_id == self.dso.id:
        grid_balance -= trade.quantity
    elif trade.seller_id == self.dso.id:
        grid_balance += trade.quantity

# inside the stage-2 loop
if buy_order.agent_id == self.dso.id:
    grid_balance -= proposed_quantity
elif sell_order.agent_id == self.dso.id:
    grid_balance += proposed_quantity

# after stage 3
self.dso.balance = grid_balance
```

**Why it is wrong.** [P1] eq. 7: $B_{\text{DSO}} = \sum (E_{\text{sold}} - E_{\text{bought}})$ over the DSO's
trades. The balance here changes only for DSO trades made in stage 1 or stage 2.
But stage 2 never contains a DSO order (the DSO places none), and stage 1 has one
only when an agent names the DSO as partner, which the rule-based partner choice
never does. Stage 3, where *all* DSO trades normally happen, does not touch
`grid_balance`. So `dso.balance` stays at its start value, 0, for the whole episode
(T4). It also carries over from step to step (it is passed back in as the next
step's start), so it is not a per-period quantity either.

**In `marlem-clean`.** `Dso.settle` computes eq. 7 from every DSO trade, per step
and over the day, with the DSO's revenue and fees
([dso.py](../../core/market/dso/dso.py#L225)).

### I-25: two opposite sign conventions for the DSO balance

**Code · Fixed**

[`src/market/matching.py` L261-L266 vs L630-L633](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L626-L633)

```python
# match_orders: by the DSO's trade
if trade.buyer_id == self.dso.id:
    grid_balance -= trade.quantity      # DSO buys  -> balance down
elif trade.seller_id == self.dso.id:
    grid_balance += trade.quantity      # DSO sells -> balance up

# _match_preferred_partners: by the agent's order
if order.is_buy:
    grid_balance -= order.quantity      # agent buys = DSO sells -> balance down
else:
    grid_balance += order.quantity      # agent sells = DSO buys -> balance up
```

**Why it is wrong.** The same DSO-preferred trade is counted with opposite signs
in the two functions: when the DSO sells, `match_orders` raises the balance and
`_match_preferred_partners` lowers it. Which one a trade passes through decides
the sign.

**In `marlem-clean`.** One convention everywhere: sold − bought, so + means the
market imported from the DSO.

### I-23: the market balance $B_{\text{grid}}$ is never computed

**Fidelity · Fixed**

[`src/environment/lem.py` L472](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L472),
[`src/environment/observation.py` L285](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L285)

```python
"grid_balance": self.dso.balance,     # info
matching.grid_balance,                # observation (= dso.balance)
```

**Why it is wrong.** [P1] eq. 20 defines the grid balance as
$B_{\text{grid}} = \sum_i (G_i - D_i + E_{\text{bought},i} - E_{\text{sold},i})$ over the agents. The code never
computes it. Every "grid balance" in the info, the observation, the reputation and
the reward is the DSO balance, which is itself always 0 (I-24).

**In `marlem-clean`.** `grid_balance_kwh` is the energy offered minus the energy
asked in the step's orders ([lem.py](../../core/market/lem.py#L177)). It is taken
*before* stage 3 on purpose: after the DSO clears every order, eq. 20 is 0 by
construction.

### I-28: grid fees are computed but never charged

**Fidelity · Fixed**

[`src/market/dso.py` L342-L345](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L342-L345),
[`src/market/matching.py` L319-L332](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L319-L332)

```python
# DSOAgent.calculate_fees
total_fee = congestion_fee + transmission_fee + imbalance_fee + voltage_fee + thermal_fee + zone_bonus
self.fees += total_fee
return total_fee

# stage 2: the fee is stored on the trade
grid_fees = self.dso.calculate_fees(buy_order, sell_order, trade_price, proposed_quantity)
trades.append(Trade(..., distance, transmission_loss, grid_fees))
```

**Why it is wrong.** The fee (eq. 8) is computed, added to the DSO's own counter
and stored on the trade, and then nothing reads it. Settlement
(lem.py L404-L423) uses only the trade quantities, and the agents' profit is never
updated anyway (I-27). No agent ever pays a fee, so the fees cannot shape any
incentive, which is their purpose in [P1].

**In `marlem-clean`.** The DSO puts the fee on every trade and says who pays it,
split 50/50 between peers or paid in full by the participant on a DSO trade.
Settlement takes it off profit, and the DSO collects it
([dso.py](../../core/market/dso/dso.py#L178-L204)):

```python
fees = sum(t.buyer_fee for t in trades if t.buyer_id == self.id)
fees += sum(t.seller_fee for t in trades if t.seller_id == self.id)
# ...
profit -= fees
```

### I-29: $F_{\text{trans}}$ has no formula, and the code uses 0

**Paper · Decided**

<mark class="review">Review</mark> How to calculate transmission fee? what examples are used in other literature?

[`src/market/dso.py` L293, L314](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L293-L314)

```python
transmission_fee = 0.0
# ...
# Calculate transmission distance and fee
distance = buy_order.location.distance_to(sell_order.location, self.grid_network.graph) if ...
```

**Why it is wrong.** [P1] eq. 8 lists $F_{\text{trans}}$ among the fee parts but gives no
formula. The code computes the trade's distance under the comment "calculate
transmission distance and fee", then never uses it for a fee: `transmission_fee`
stays 0. (The distance does feed the voltage fee.)

**In `marlem-clean`.** The form is set; its values are open. [P1] gives two
hints. The text of eq. 8 calls $F_{\text{trans}}$ a charge for "usage per unit of
distance of the transmission lines (predefined by the DSO)", and §3.5.2 says the
losses "are incorporated into trading fees". Both give a fee of quantity ×
distance × a price factor. Here it is the lost energy (eq. 18) at the trade price
([dso.py](../../core/market/dso/dso.py#L137)):

$$
F_{\text{trans}} = l_{ij}\, p_{ij} = \kappa\, d_{ij}\, q_{ij}\, p_{ij}
$$

Still to choose: the price factor ($\kappa\, p_{ij}$, or a fixed tariff per kWh
and km as in the MW-mile method) and the distance (line length now; an
impedance-based electrical distance is an option). The same fee applies to trades
with the DSO, along the path to the transformer (I-54).

### I-30: $F_{\text{volt}}$ is gated by its threshold and capped at 0.2

**Fidelity · Decided**

[`src/market/dso.py` L326-L333](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326-L333)

```python
voltage_drop = distance * self.voltage_factor
if voltage_drop > self.voltage_threshold:
    voltage_fee = min(0.2, voltage_drop) * quantity * trade_price

if congestion_level > self.instability_threshold:
    thermal_factor = (congestion_level - self.instability_threshold) / (1.0 - self.instability_threshold)
    thermal_fee = min(0.3, thermal_factor) * quantity * trade_price
```

**Why it is wrong.** [P1] eq. 8c is $F_{\text{volt}} = \min(V_{\text{drop}}, V_{\text{threshold}}) \cdot q \cdot p$:
the threshold is the *cap*, and the fee is charged from the first metre. The code
uses the threshold as a *gate* (no fee at all below 0.05) and a different cap
(0.2). On a low-voltage feeder, where trades are a few hundred metres apart,
$V_{\text{drop}} = 0.15 \cdot 0.2\ \text{km} = 0.03$ is below the gate, so the voltage fee is always
0. The thermal cap 0.3 is $f_{\text{threshold}}$ of eq. 8d, which [P1] leaves undefined.

**In `marlem-clean`.** $F_{\text{volt}}$ exactly as eq. 8c; the thermal cap kept at the
original's 0.3 as `thermal_cap` ([dso.py](../../core/market/dso/dso.py#L137-L161)).

### I-31: the imbalance fee can never apply

**Fidelity / Paper · Decided**

[`src/market/dso.py` L336-L339](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L336-L339),
[L421-L425](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L411-L442),
[L227-L229](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226)

```python
# calculate_fees, called only for peer trades
balance_impact = self._calculate_balance_impact(buy_order.agent_id, sell_order.agent_id, quantity)
if balance_impact < 0:
    imbalance_fee = abs(balance_impact) * quantity * trade_price * self.imbalance_factor

# _calculate_balance_impact
if self.balance > 0:
    if buyer_id != self.id and seller_id != self.id:
        # P2P trade doesn't directly affect grid balance
        return 0.0

# clear_unmatched_orders: every DSO trade
dso_trades.append(Trade(self.id, sell_order.agent_id, ..., 0.0, 0.0, 0.0))  # No grid fees for DSO trades
```

**Why it is wrong.** Three pieces that cannot meet. `calculate_fees` runs only
for peer trades, and for a peer trade the balance impact is 0 by definition.
Eq. 8h defines a non-zero impact only for trades *with the DSO*, but every DSO
trade is created with a fee of 0. On top, the impact is measured on
`self.balance`, which is always 0 (I-24), so even that branch is never reached.
$F_{\text{imb}}$ is 0 in every possible run (N-04).

**In `marlem-clean`.** The imbalance fee is charged on DSO trades that worsen the
market's balance $B_{\text{grid}}$ (the DSO buying in excess demand, or selling in excess
supply); a trade that helps pays nothing ([dso.py](../../core/market/dso/dso.py#L163-L176)).

<mark class="review">Review</mark> What trade could exactly help at the same time while bringing in more of the quantity that already exists in the P2P market? I dont see a situation

### I-54: DSO trades skip the grid, and the grid check ignores direction

**Code · Fixed**

<mark class="review">Review</mark> What options do we have here? It would make sense to atleast use the feeder distance from the bus as the closest point to the DSO but im not sure if that is good enough, in any case some dynamics instead of nothing!?

[`src/market/dso.py` L224-L226, L371](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L219-L226)

```python
# every DSO trade
0.0,  # DSO is assumed to be at zero distance
0.0,  # No transmission loss with DSO
0.0)) # No grid fees for DSO trades

# validate_grid_constraints
if self.grid_network and abs(self.balance + proposed_quantity) > self.grid_network.capacity:
    return False
```

**Why it is wrong.** Energy bought from or sold to the DSO travels through the
same lines as peer energy, but DSO trades have no distance, no loss and no fee,
and are never checked against the grid. The check that does exist adds the
quantity to the balance whatever the trade's direction, so a trade that would
*reduce* an imbalance is treated as increasing it.

**In `marlem-clean`.** The DSO's energy enters where the upstream grid feeds
the network, the transformer's low-voltage busbar. A trade with the DSO runs along
the participant's path to that busbar
([powerflow.py](../../core/grid/powerflow.py#L158),
[dso.py](../../core/market/dso/dso.py#L206)). It has a distance, a loss (eq. 18)
and the fees of that path: congestion and thermal on its lines, voltage and
transmission by its length. It gets no zone bonus, since the DSO is in no
participant's zone. A neighbour is closer than the transformer, so a peer trade
pays less in fees than a trade with the DSO: the local incentive of [P1] §3.5.2.
In the notebook's example day the DSO trades pay about 1.4 in fees, the peer
trades about −1.1 (notebook check "DSO trade runs to the transformer").

No trade is blocked for grid reasons (I-55): the fees penalize, and the power flow
shows the physical result of all energy.

### I-74: the thermal fee starts far below the congestion fee

**Paper · Flagged**

<mark class="review">Review</mark> How is this usually handeled in real life? Who is to say that the thermal fee cant start much earlier, I understand congestion might be more important but they are different effects.

[`src/market/dso.py` L65-L67](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L65-L67)

```python
self.congestion_threshold: float = 0.8  # Threshold for congestion intervention
self.voltage_threshold: float = 0.05  # Threshold for voltage drop
self.instability_threshold: float = 0.2  # Threshold for grid stability
```

**Why it is wrong.** The thermal fee (eq. 8d, 8g) starts at 20 % line loading,
the congestion fee (eq. 8a) at 80 %. A line at 50 % already pays a thermal fee for
"thermal instability" while it is far from congested. [P1] gives no values; these
are the original's.

**In `marlem-clean`.** Kept as defaults (`thermal_threshold`,
`congestion_threshold`), each its own setting.

Real distribution grids have no fee that starts at 20 % loading. "Congestion" means
loading beyond a line's thermal rating, and operators act near that limit, for
example through flexibility markets such as the Dutch GOPACS. The thermal costs
underneath grow smoothly: losses with the square of the current, transformer
ageing steeply above rated load.

In the model the two fees are not separate effects anyway: eq. 8a and 8g read the
same loading $C_t$. Together they form one fee that rises with loading in two
steps, gently from $T_{\text{threshold}}$ and steeply from $C_{\text{threshold}}$
(with $x^+ = \max(x, 0)$):

$$
\frac{F_{\text{thermal}} + F_{\text{cong}}}{q_{ij}\, p_{ij}} =
\min\!\left(\frac{(C_t - T_{\text{threshold}})^+}{1 - T_{\text{threshold}}},\
f_{\text{threshold}}\right) + f_{\text{cong}}\, (C_t - C_{\text{threshold}})^+
$$

The values are set once the episode runs show how loaded the lines of SimBench's
LV networks get. Below about 30 % loading both parts are close to 0, and the
choice does not matter.

### N-05: the same-zone bonus outweighs every fee

**Paper · Flagged**

[`src/market/dso.py` L317-L319, L72](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317-L319)

```python
self.zone_factor: float = 0.15  # Factor for cross-zone fees
# ...
if buy_order.location and sell_order.location and buy_order.location.zone == sell_order.location.zone:
    zone_bonus = -quantity * trade_price * self.zone_factor
```

**Why it is wrong.** A same-zone trade gets 15 % of its value back. On a
low-voltage feeder the other fees are small: the voltage fee is about 3 % of the
value (once charged as eq. 8c), the loss fee less than 1 %, and congestion and
thermal fees are 0 at normal loading. Total fees are therefore **negative**: the
DSO pays peers to trade locally. In the notebook's example day the peer trades'
fees add up to about −1.1: a zone bonus of −1.6 against 0.5 of other fees. [P1]
gives no factor values; whether a subsidy is intended is not said.

**In `marlem-clean`.** Kept at the original's 0.15 for now. `zone_factor` is one
setting, and its value is open: it should be of the size of the other fees, a few
percent of a trade's value.

### N-06: zones exist only for the paper's graphs

**Paper · Flagged**

<mark class="review">Review</mark> I need suggestions here on options to see if they make sense, Im not sure how zones make sense on these small scale experiments but then again simbench has large networks also, how big were the zones for salazar or did he even use them?

[`src/market/dso.py` L317](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L317)

```python
buy_order.location.zone == sell_order.location.zone
```

**Why it is wrong.** [P1] §3.5.4 defines zones as connected parts of its graph
topologies (mesh, ring, line, IEEE feeders). A real distribution network has no
such labels, so the zone bonus needs a definition that fits it.

**In `marlem-clean`.** A zone is a feeder: the branch a bus hangs on, named by the
first bus after the transformer's low-voltage busbar
([powerflow.py](../../core/grid/powerflow.py#L190)).

[P2] did use zones: its case study divides IEEE-34 into six named zones
(substation, transformer, feeder 1 and 2, lateral 1 and 2) for 8 agents. Its zones
are branches of the feeder, as here. On SimBench's networks they hold a few to a
few dozen loads:

| Network | Zones with loads | Loads per zone |
|---|---|---|
| `1-LV-rural1--0-sw` | 4 | 1, 3, 4, 5 |
| `1-LV-semiurb4--0-sw` | 3 | 5, 8, 26 |
| `1-LV-urban6--0-sw` | 7 | 1 to 16 |
| `1-MV-rural--0-sw` | 9 | 1 to 18 |

A zone's only effect is the bonus of eq. 8e: a trade within one zone pays
$f_{\text{zone}}$ of its value less. Regulators do something similar: Austria's
Renewable Expansion Act (EAG, 2021) cuts grid charges more for local energy
communities (low-voltage level) than for regional ones. How large the bonus should
be is the open question of N-05.

## 7. Grid model used by the market

### I-33: edge flows start random and pile up all episode

**Fidelity · Replaced**

[`src/grid/network.py` L85, L322-L325](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L84-L85)

```python
# at construction
self.edge_flows[(u, v)] = np.random.uniform(0, 0.3) * edge_capacity

# update_flow_from_trade, for every trade on the path
self.edge_flows[key] += power_at_edge
self.edge_flows[key] = float(min(self.edge_flows[key], self.edge_capacities[key]))
```

**Why it is wrong.** Each line starts at a random 0-30 % of its capacity, and
every trade *adds* its energy to the lines on its path. Nothing ever resets or
reduces the flows, so congestion only grows within an episode (T10) until lines sit
at the capacity cap. [P1] §3.5.3 describes a per-period update; congestion here
measures the episode's history, not the current period.

**In `marlem-clean`.** One AC power flow per step on a fresh state of the network
([powerflow.py](../../core/grid/powerflow.py#L105)).

### I-32: only stage-1 trades reach the grid

**Fidelity · Replaced**

[`src/market/matching.py` L575](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L569-L577),
[L346-L353](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L325-L332)

```python
# _create_trade (used by stage 1 only)
self.grid_network.update_flow_from_trade(buyer_node, seller_node, proposed_quantity)

# stage 2 builds its trades directly, without it
trades.append(Trade(buy_order.agent_id, sell_order.agent_id, trade_price, ...))
```

**Why it is wrong.** The flow update lives in `_create_trade`, which only stage 1
calls. Stage 2, where most peer trades happen, appends `Trade(...)` objects itself
and never updates the flows. So the congestion the fees and the grid check rely on
ignores almost all peer energy.

**In `marlem-clean`.** The flow comes from each participant's physical injection
at its bus, whichever stage its trades came from.

### I-57: the IEEE-34 graph is disconnected

**Fidelity · Replaced**

[`src/grid/config.py` L29-L39](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/config.py#L29-L39)

```python
"edges": [("800", "802", 0.486), ("802", "806", 0.527), ("806", "808", 0.932),
          # ...
          ("852", "832", 0.21), ("854", "856", 0.157), ("854", "852", 0.621),
          ("858", "864", 0.496), ("858", "834", 1.774), ("860", "836", 0.268),
          ("862", "838", 0.223), ("888", "890", 1.584)],
```

**Why it is wrong.** In the IEEE 34-node feeder, node 888 hangs off node 832
through the in-line transformer. The edge 832-888 is missing, so 888 and 890 form
an island (T13): agents there have no path to anyone, and distances to them fall
back to Euclidean (I-53). The impedance table defined next to the edges is never
used.

**In `marlem-clean`.** SimBench networks.

### I-70: the grid physics is linear and unbounded

**Paper · Replaced**

[`src/grid/network.py` L348](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L348),
[`src/market/dso.py` L326](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/dso.py#L326)

```python
return distance * quantity * np.clip(loss_factor, 0.0, 1.0)   # loss
voltage_drop = distance * self.voltage_factor                  # voltage drop
```

**Why it is wrong.** Losses grow linearly with $d \cdot q$ instead of with the square
of the current, and once $d \cdot \kappa > 1$ a trade loses more than it carries. The
voltage drop is a distance times a constant, independent of the load. Flows are
quantities moved along graph edges, not power flow. [P1] nevertheless calls its
grid "high-fidelity". This is the paper's model, not a coding slip.

**In `marlem-clean`.** The physics is a pandapower AC power flow. The paper's
linear forms remain only inside the market's fee formulas (eq. 8f, eq. 18), where
[P1] defines them.

### I-53: defensive code hides bad state

**Code · Replaced**

[`src/grid/network.py` L38, L95](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L38-L38),
[`src/grid/base.py` L51-L57](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/base.py#L51-L57)

```python
self.capacity = max(0.0, capacity)
# ... in _check_init, which can now never fail:
if self.capacity < 0:
    raise ValueError(...)

try:
    return nx.shortest_path_length(graph, source=self.node_id, target=other.node_id, weight='weight')
except:
    return self._euclidean_distance(other.x, other.y)
```

**Why it is wrong.** A negative capacity is silently turned into 0 before the
check that should reject it. Any failure of the shortest path (a disconnected
graph, I-57, or a wrong node ID) silently becomes a straight-line distance in
made-up coordinates, so the fee and loss calculations go on with a number that
has nothing to do with the grid.

**In `marlem-clean`.** The grid code is new. Elements reject impossible settings
instead of correcting them (`Battery._check`, `Scenario.problems()`), and a missing
bus raises an error ([powerflow.py](../../core/grid/powerflow.py#L105)).

### I-14: losses are topped up from the DSO

**Fidelity · Decided**

[`src/market/matching.py` L347](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L347),
[`src/environment/lem.py` L397-L401](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L397-L401)

```python
# stage 2
buy_order.quantity -= (proposed_quantity - transmission_loss)  # Buyer receives less due to losses

# settlement
for trade in matching_result.trades:
    if trade.buyer_id == id:
        energy_bought += trade.quantity
```

**Why it is wrong.** The buyer's order is reduced by less than the trade, so the
lost part stays open on the buyer's order and is then bought from the DSO in
stage 3. The buyer pays the DSO for the peer trade's losses, while settlement
counts the full trade quantity as delivered. The household receives $q$ from the
peer *and* the loss from the DSO, so energy bought exceeds what the agent needed.
[P1] says only that the loss "derates the delivered quantity".

**In `marlem-clean`.** The market is lossless. Each trade **records** its loss
(eq. 18) and pays for it in the fee (I-29); the physical losses are the power
flow's.

### I-34: the loss factor is hard-coded

**Code · Fixed**

[`src/grid/network.py` L331-L334](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/grid/network.py#L331-L334),
[`src/market/matching.py` L316](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L316)

```python
def transmission_loss(self, distance: float, quantity: float,
                      loss_factor: float = 0.03) -> float:

# the caller never passes it
transmission_loss = self.grid_network.transmission_loss(distance, proposed_quantity)
```

**Why it is wrong.** $\kappa$ of eq. 18 is a default argument that no caller sets and no
configuration reaches, in "distance units" of whatever graph is used. [P1] gives
no value.

**In `marlem-clean`.** `loss_factor` is a DSO setting, per km of line
([scenario.py](../../core/config/scenario.py#L172)). Every trade also records its
distance $d_{ij}$, along the network's lines.

## 8. Reputation

### I-38a: reliability is always 1

**Fidelity · Fixed**

[`src/market/reputation.py` L125-L129](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L124-L129),
[`src/market/matching.py` L382](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L380-L382)

```python
# ReputationHandler._calculate_reputation, STEP 1
agent_trades = [t for t in matching_result.trades if t.buyer_id == agent.id or t.seller_id == agent.id]
agent_unmatched = [o for o in matching_result.unmatched_orders if o.agent_id == agent.id]
reliability = len(agent_trades) / (len(agent_trades) + len(agent_unmatched)) if ... else self._neutral

# OrderMatcher.match_orders, what it passes in
# DSO is always active, so all orders should be matched
unmatched_orders = []
```

**Why it is wrong.** The definition reads sensibly: trades over trades plus
unmatched orders. But the matcher always passes an **empty** list of unmatched
orders, because the DSO clears everything. So for any agent with a trade,
reliability is $n / (n + 0) = 1$. [P1] eq. 12 calls it "the ratio of matched to
total order volume", and it never varies.

**In `marlem-clean`.** Order volume matched by peers ÷ order volume
([reputation.py](../../core/market/reputation.py#L193-L197)).

### I-38b: the decay follows the time of day

**Fidelity · <mark>Decided</mark>** (marlem-v1)

<mark class="review">Review</mark> If and what formula to use? Just reverse salazars to the proper form?

[`src/market/reputation.py` L86-L87](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L86-L87),
[`src/environment/lem.py` L436, L441](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L436-L441)

```python
new_reputation = self._calculate_reputation(agent, matching_result, dso_id)
return (time_of_day * agent.reputation) + ((1.0 - time_of_day) * new_reputation)

# the caller
self.time_of_day = (self.current_step % self.max_steps) / self.max_steps
agent.reputation = self.reputation_handler.update_reputation(agent, matching_result, self.time_of_day)
```

**Why it is wrong.** [P1] §3.3.4 updates the reputation "incorporating a decay
factor to weigh recent behavior more heavily". Here the weight of the old
reputation is the time of day. In the first hour the old reputation counts 1/24
and the new score almost everything; in the last hour the old reputation counts
23/24 and that hour's behaviour almost nothing. Recent behaviour weighs *less* as
the day goes on, the opposite of the paper.

**In `marlem-clean`.** A constant decay, $r \leftarrow 0.8\, r + 0.2\, \text{score}$, in
`update_reputation` ([reputation.py](../../core/market/reputation.py#L119-L142)).

**Decided (marlem-v1).** A constant decay per **hour**, applied per step as
$\delta = 0.8^{\Delta t}$ with $\Delta t$ the step length in hours
([lem.py](../../core/market/lem.py#L233-L238)). Reversing the original's weights
would still tie the memory to the hour of the day; a per-hour decay keeps the
memory the same when the step length changes (I-56). With 0.8 the old reputation
halves in about 3.1 hours ($\ln 0.5 / \ln 0.8$), whether the step is an hour or a
quarter of an hour. Hourly scenarios behave exactly as before.

### I-38c: the grid part is always neutral, and fairness mixes in the DSO

**Fidelity / Code · Fixed**

[`src/market/reputation.py` L133, L146, L185-L191](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L131-L191)

```python
# STEP 2, fairness: every trade of the agent, DSO trades included
price_deviations = [abs(t.price - matching_result.clearing_price) / matching_result.clearing_price
                    for t in agent_trades if matching_result.clearing_price > 0]

# STEP 3, grid: measured on matching_result.grid_balance (= dso.balance)
impact = self._calculate_grid_impact(agent.id, trade, matching_result.grid_balance, dso_id)

# _calculate_grid_impact
if abs(grid_balance) < 0.1:
    return 0.0
if (trade.buyer_id == dso_id) or (trade.seller_id == dso_id):
    # DSO trades are always stabilizing by definition
    return self._neutral
```

**Why it is wrong.**

- **The grid part never moves.** It is measured on `grid_balance`, which is the
  DSO balance and always 0 (I-24). `abs(0) < 0.1` returns 0 for every trade, which
  maps to the neutral 0.5. The grid part has the largest weight (0.5), so half of
  the reputation is a constant.
- **A DSO trade counts as helping (N-03).** The function returns values from −1 to
  1, and 0 is neutral. For DSO trades it returns `self._neutral`, which is 0.5:
  "neutral" on the 0-1 scale, but a positive, helping impact on this one. (This
  branch is reached only once the balance is fixed.)
- **Fairness compares with the DSO's tariffs (N-02).** The fairness part compares
  every trade of the agent, DSO trades included, with a clearing price that
  includes the DSO's tariffs (I-16). An agent forced to the DSO at night looks
  "unfair" for a price it did not choose.

**In `marlem-clean`.** The grid part uses the step's $B_{\text{grid}}$, and DSO trades count
0. Fairness uses the agent's peer trades against the peer clearing price
([reputation.py](../../core/market/reputation.py#L199-L230)).

### I-07: every agent gets the same "random" initial reputation

**Code · Decided**

<mark class="review">Review</mark> I started pondering about the reputation mechanism, it is a good feature and so on and makes sense to keep it and i want to but in the span of a single day especially if its dynamic, not sure how to handle this and like maybe the day is too short to make it meaningful, because very dependent on initial conditions.

[`src/market/reputation.py` L65-L68](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/reputation.py#L56-L68),
[`src/environment/lem.py` L281-L283](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L281-L283)

```python
def reset(self, seed: int = None) -> float:
    if seed is not None:
        np.random.seed(seed)
    return np.random.uniform(0.0, 1.0)

# the caller, once per agent with the same seed
for agent in self._agents.values():
    reputation = self.reputation_handler.reset(seed)
```

**Why it is wrong.** The global random generator is reseeded with the *same*
seed before every agent's draw, so every agent draws the same number. The start
looks random but is identical for all, and it also resets the global random state
everything else uses. [P1] does not say how reputation starts.

**In `marlem-clean`.** Everyone starts at 0.5. `reset` is kept with its own random
generator (`np.random.default_rng(seed)`), but is not used.

## 9. Trade ledger

### I-66: the block hash leaves out losses and fees

**Code · Flagged**

[`src/market/validation.py` L25-L34](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/validation.py#L25-L34),
[`src/market/matching.py` L395-L396](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/market/matching.py#L395-L396)

```python
block_content = {"timestamp": self.timestamp,
                 "previous_hash": self.previous_hash,
                 "trades": [{"buyer_id": trade.buyer_id,
                             "seller_id": trade.seller_id,
                             "price": float(trade.price),
                             "quantity": float(trade.quantity),
                             "timestamp": float(trade.timestamp)} for trade in self.trades],
                 "nonce": self.nonce}

# match_orders: a block is forced at the end of every step
if self.validator.pending_trades:
    self.validator._create_new_block()
```

**Why it is wrong.** The hash covers who traded what at which price, but not the
trade's distance, loss or fee. Those could be changed after the fact without
breaking the chain. The matcher also calls the validator's *private*
`_create_new_block` to force one block per step, and the "proof of work" is a loop
in one process, not a consensus between parties. [P1] §3.3.4 presents it as an
emulation, which is fair, but the hash should cover everything that moves money.

**In `marlem-clean`.** Out of scope for now: the ledger changes no market result.
The validator is kept as in the original; once the ledger matters, its hash should
cover each trade's distance, loss and fee.

**In `marlem-clean`.** Original code, with a public `seal_block` in place of the
private call; off by default (`ledger_difficulty = 0`). Now that fees are charged,
the hash should cover them.

## Problems in the paper's market method

What the paper itself leaves wrong or open, whatever the code does. Each row needs a
recorded decision, because the paper cannot settle it.

| Topic | The problem in [P1] | Issues |
|---|---|---|
| Battery (eq. 15–16) | Eq. 15c-d ignores the efficiencies; the text claims rate limits that eq. 16 does not have | I-71 |
| Grid fees (eq. 8) | $F_{\text{trans}}$ has no formula. No fee factor has a value. The thermal threshold sits below the congestion threshold. Eq. 8c uses the "threshold" as a cap | I-29, I-30, I-74, N-05 |
| Imbalance fee (eq. 8b, 8h) | Defined only for trades with the DSO; whether those pay fees is not said | I-31 |
| $B_{\text{grid}}$ (eq. 20) | Its timing is not given. After the DSO clears every order it is 0 by construction, so it only means something before stage 3 | I-23 |
| Clearing price | Not defined. The original mixed peer prices with the DSO's tariffs | I-16 |
| Stage 1 | The DSO-preferred sub-stage the original added is not in the paper | I-15 |
| Pricing | The case study's bid-ask spread mechanism is not among the mechanisms of §3.3.3 | I-17 |
| Reputation (eq. 12) | Weights and decay factor have no values; "fairness" and "grid contribution" have no formulas | I-38 |
| Grid physics | Linear, unbounded losses and voltage drop, called "high-fidelity". Capacity violations "can be penalized or disallowed", with no choice made (penalized here) | I-70, I-55 |
| Zones | Defined for graph topologies only | N-06 |
| Units | \$/MWh in the case study, kWh per implicit 1-hour step | I-56 |

## What this means for the published results

[P1]'s Case 5 (batteries with zero-intelligence agents) ran on this market. If the
paper's figures were produced with the original code, which cannot be confirmed
independently:

- **The P2P prices in Fig. 5 are the buyers' bids.** The case uses `BID_ASK_SPREAD`,
  which returned the buyer's price (I-17).
- **The batteries did not behave as described.** Selling charged them (I-18),
  discharge drained less than it delivered (I-20), and a charge reaching $SoC_{\max}$ was
  refused entirely (I-19).
- **No money moved:** no profit (I-27), no fees (I-28), no DSO balance (I-24).

So the paper's conclusion that batteries stabilise prices is **not supported** by the
original market. A thesis built on `marlem-clean` is a corrected reimplementation
of the paper's market, not a reproduction of its results.

## Outside this document

The register's other IDs belong to the RL layer. The training paradigms, trainer and
inference are in [rl.md](rl.md); the rest belong to the connection between the market
and the RL layer:

- **Actions and observations:** I-10, I-39, I-40, I-58
- **Reward:** I-02, I-41 to I-47, I-75, I-76, I-79
- **KPIs:** I-35 to I-37, I-65, I-68, I-69
- **Paradigms, training and inference:** I-48 to I-50, I-59 to I-62, I-73
- **Experiments and reproducibility:** I-03, I-04, I-51, I-63, I-64, I-72, I-80
- **Tests and docs:** I-52, I-67
