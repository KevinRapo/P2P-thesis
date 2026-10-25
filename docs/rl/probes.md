# How the probes work

The probes check the RL layer before it meets the market: tiny environments whose
right answer is known exactly, trained with the same PPO, paradigms and settings
as the market, and judged by reading the trained networks. When a probe fails,
the piece it adds is the one to look at.

Probes 1-5 follow Andy Jones's guide,
[Debugging RL, Without the Agonizing Pain](https://andyljones.com/posts/rl-debugging.html),
made multi-agent and continuous. Probes 6-10 are this implementation's own: each
one isolates a feature of the market's action or horizon, so a failure on the
market can be traced to the feature behind it.

| Where | What |
|---|---|
| [`core/rl/envs/probes.py`](../../core/rl/envs/probes.py) | The probe environments and their checks |
| [`core/rl/scripts/probe_check.py`](../../core/rl/scripts/probe_check.py) | The procedure: the probes' settings and budgets, training in one pool, scoring, longer budgets for failures |
| [`core/rl/scripts/probe_ppo.py`](../../core/rl/scripts/probe_ppo.py) | The procedure as one command |
| [`notebooks/rl/probe_paradigms.ipynb`](../../notebooks/rl/probe_paradigms.ipynb) | The same procedure, probe by probe, here or in the cluster's Jupyter job |

## What every probe has in common

**The agents.** Three agents by default, each with its own reward. Each observes
one number in $[-1, 1]$ and acts with one number in $[-1, 1]$, or with a `Dict` of
parts in probes 6-9, like the market's action. From probe 4 on, the agents are
named `agent_2`, `agent_10`, `agent_1` (`scramble_ids`), so their sorted order
differs from their order in the environment, and each agent has a different
target. An observation, action or reward delivered to the wrong agent then gives a
wrong answer. That is the defect L-05 found in the original's grouping.

**An episode.** A probe defines four things on a common base
([`_Probe`](../../core/rl/envs/probes.py#L98-L178)): the observation of each step
(`_draw`), the reward of an action (`_reward`), the episode's length (`length`:
1 step, 2 in probe 3, 24 in probe 10) and its checks (`checks`). An episode ends by
termination after `length` steps, never by truncation.

**What a run must output.** A probe's `checks` list states, each with the value
and the action the trained networks must give there
([`Check`](../../core/rl/envs/probes.py#L74-L95)). A run is judged by reading its
networks in those states, not by its return, which mixes in exploration noise:

| Output | Read as | Passes when |
|---|---|---|
| Value | the critic's $V$; in CTCE the group's value, compared with the **sum** of the agents' values (its reward is the sum) | within $0.15 \cdot \max(1, |V|)$, or $0.15 \cdot |V|$ for a check marked `relative` |
| Continuous action part | the Gaussian's mean (clipped to the bounds, as the environment receives it) | within 0.15 |
| Categorical action part | the most likely category | exactly the expected one |
| A part expected as `None` | not judged | always |
| A part expected as `Follows` | its target depends on the category the policy chose for another part | within 0.15 of that target |

The comparison is a plain function,
[`compare`](../../core/rl/scripts/probe_check.py#L274-L320), so it is tested
without training.

**How much training.** Each probe has a budget in environment steps for the
`"fast"` preset (a 2 × 64 network, learning rate $10^{-3}$, batches of 500,
minibatches of 64, 10 epochs); `"thorough"` uses RLlib's 2 × 256 network, learning
rate $3 \cdot 10^{-4}$ and twice the budget
([`PRESETS`](../../core/rl/scripts/probe_check.py#L126-L145)). Every other setting is
the market's ([`rl_defaults.py`](../../core/rl_defaults.py)), including the gradient
clip of 0.5 and the entropy coefficient of 0.01.

**Reading a result.**

- **Pass at the budget:** the piece the probe adds works.
- **Pass only at a larger budget:** it works, slowly. `escalate` trains every
  failing combination again at 2×, 4×, 8× the budget and reports the smallest that
  passed.
- **Never passes, or gets further away with more steps:** something structural:
  the learner, the action's distribution or the probe's own design. The per-part
  diagnostics in each run's `metrics.csv` (each action part's mean, log σ and
  share outside the bounds, or its entropy; the gradient norm; the KL of each
  update) show which; the Studio's Results page plots them in its Learning tab.

## The probes at a glance

| # | Name | Action | Reward | What it adds | Exact answer |
|---|---|---|---|---|---|
| 1 | Constant | ignored | +1 | value learning | $V = 1$ |
| 2 | Observation | ignored | the own observation | the critic reads its input | $V(o) = o$ |
| 3 | Discount | ignored | +1 at the end of 2 steps | discounting | $V(0) = \gamma$, $V(1) = 1$ |
| 4 | Action | `Box` | $1 - (a - t_i)^2$ | the policy gradient | mean $= t_i$ |
| 5 | Obs → action | `Box` | $1 - (a - o/2)^2$ | the policy reads its input | mean $= o/2$ |
| 6 | Mixed action | category + level | $[c = c_i] + 1 - (l - t_i)^2$ | a categorical and a continuous part at once | $c_i$, $t_i$ |
| 7 | Gated action | category + gate | closed 0.2; open $[c = c_i](1 - (g - 0.5)^2)$ | a part that counts only when another allows it | $c_i$, gate 0.5 |
| 8a | Mutual choice, coordination | side + partner, pairs | mutual naming 1, DSO 0.1, else 0; +0.1 own side | coordinating with a partner | own side, mate |
| 8b | Mutual choice, stag hunt | the same | DSO 0.5 instead of 0.1 | the market's coordination problem | measured, not judged |
| 9 | Conditional part | side + level | $1 - (l - t_\text{side})^2$ + 0.05 own side | a part whose best value depends on another part | the level of the chosen side |
| 10 | Long episode | ignored | +1 at the last of 24 steps | the market's day | $V(t) = \gamma^{23 - t}$ |

---

## Probes 1-5: Andy Jones's sequence

Jones's five probes each add one piece of a learning problem to the previous one:
value learning, then observations, then time, then actions, then actions that
depend on observations. His have discrete actions and one agent; here the action is
continuous (the market's price and quantity are) and there are three agents with
their own rewards, so each probe also checks that every agent's data reaches its
own networks, in each paradigm.

### 1. Constant

**Definition.** Observation 0, one step, reward +1 whatever the action
([`ConstantProbe`](../../core/rl/envs/probes.py#L181-L190)).

**What it tests.** That the reward reaches the learner, that the episode's end is
treated as final, and that the value loss and the optimiser can fit a constant.
Nothing depends on the observation or the action.

**Expected.** $V = 1$ per agent ($3$ for CTCE's group). Any working learner
reaches it almost exactly.

### 2. Observation

**Definition.** Each agent observes $+1$ or $-1$ at random; reward = its own
observation; one step ([`ObservationProbe`](../../core/rl/envs/probes.py#L192-L216)).

**What it tests.** That the observation reaches the critic, and the right agent's
critic. Checked in three states: all $+1$, all $-1$, and mixed ($+1, -1, +1$); a
critic that ignores its input, or reads another agent's observation, gets the
mixed state wrong.

**Expected.** $V(o) = o$ per agent, the sum for the group.

### 3. Discount

**Definition.** Two steps: observation 0, then 1; reward 0, then +1; trained with
$\gamma = 0.5$ ([`DiscountProbe`](../../core/rl/envs/probes.py#L218-L237)).

**What it tests.** Bootstrapping from the next state, the discount, and where the
episode ends.

**Expected.** $V(1) = 1$ and $V(0) = \gamma = 0.5$ per agent.

### 4. Action

**Definition.** Observation 0, one step, reward $1 - (a_i - t_i)^2$ with targets
$t_i = -0.6, 0, 0.6$ for the three agents
([`ActionProbe`](../../core/rl/envs/probes.py#L239-L249)).

**What it tests.** The policy gradient, and that each agent's action reaches its
own reward.

**Expected.** Each agent's action mean at its target. For a Gaussian policy with
mean $\mu$ and spread $\sigma$ the expected reward is
$1 - (\mu - t)^2 - \sigma^2$, highest at $\mu = t$ whatever $\sigma$, so the mean
is a clean read-out while the policy still explores. A small overshoot towards the
bounds is expected: samples beyond $\pm 1$ are clipped to the bound and earn its
reward, which pulls the mean outwards.

### 5. Obs → action

**Definition.** Each agent observes $\pm 1$ at random; reward
$1 - (a_i - o_i/2)^2$; one step
([`ObsActionProbe`](../../core/rl/envs/probes.py#L251-L275)).

**What it tests.** That each agent's policy uses its own observation, and that
observation, action and reward stay aligned through batching.

**Expected.** Action mean $= o/2$ ($\pm 0.5$) in the same three states as probe 2.
CTCE is the slowest here: one network must learn which observation matters for
which agent from the summed reward (L-02).

---

## Probes 6-10: the market's action and horizon

The market's action is a `Dict` of four parts ([P1] eq. 2): side and partner are
categorical, quantity and price continuous. RLlib gives each part its own
distribution and adds their log-probabilities, and the policy samples the parts
independently of each other ([RL layer](../v2.md)). Probes 6-10 test what that
means for the market, one feature at a time.

### 6. Mixed action

**Definition.** Observation 0, one step, action `{"choice": Discrete(3), "level":
Box(-1, 1)}`; reward $[\text{choice} = c_i] + 1 - (\text{level} - t_i)^2$, with a
different category $c_i$ and level $t_i$ per agent
([`MixedActionProbe`](../../core/rl/envs/probes.py#L277-L330)).

**Why the market needs it.** Every market action has categorical and continuous
parts. This is the smallest case: one of each, independent, each with its own
answer.

**Expected.** The most likely choice is $c_i$ (exactly), the level's mean is $t_i$,
and $V = 2$. In CTCE the group's action is a `Tuple` of these `Dict`s, so it also
checks that RLlib's composite distribution keeps each agent's parts apart.

### 7. Gated action

**Definition.** Observation 0, one step, action `{"choice": Discrete(3), "gate":
Box(-1, 1)}`. A closed gate ($g < 0$) pays 0.2 whatever the choice; an open gate
pays $[\text{choice} = c_i] \cdot (1 - (g - 0.5)^2)$
([`GatedActionProbe`](../../core/rl/envs/probes.py#L359-L395)).

**Why the market needs it.** In the market, a quantity below the no-order
threshold places no order, and then side, price and partner have no effect at all.
They still get a gradient on those steps, from a reward they did not influence.
The probe has the same structure: the choice counts only when the gate is open.
It also has the market's local optimum: closing the gate pays 0.2 for sure, an
open gate with a random choice about $1/3$. A policy that learns the choice too
slowly can settle on never "ordering".

**Expected.** Choice $c_i$, gate mean 0.5, $V = 1$. A gate mean below 0 is the
"never order" optimum.

### 8. Mutual choice (8a and 8b)

**Definition.** Four agents in two pairs (1st with 2nd, 3rd with 4th, in agent
order), observation 0, one step, action `{"side": Discrete(2), "partner":
Discrete(3)}`: side 0 sells, 1 buys; partner 0 names the pair-mate, 1 the DSO, 2
nobody. Reward: 1 when both name each other on opposite sides; `dso_reward` for
naming the DSO; else 0; plus 0.1 for the agent's own side (the first of a pair
sells, the second buys), which makes the best answer unique
([`MutualChoiceProbe`](../../core/rl/envs/probes.py#L397-L485)).

**Why the market needs it.** Stage 1 of the clearing trades only between a buyer
and a seller that named each other. Learning that is a coordination problem: one
agent's partner choice pays only if its partner makes the matching choice. The DSO,
which takes every order at its tariffs, is the safe alternative.

**Which answer a learner should reach** depends on what the DSO pays. At the start
every choice is uniform, so naming the mate pays on average

$$
P(\text{the mate names me}) \cdot P(\text{opposite sides}) = \tfrac13 \cdot \tfrac12 = \tfrac16 ,
$$

against `dso_reward` for naming the DSO, whatever the mate does. Hence two runs:

- **8a, coordination** (`dso_reward = 0.1`, below 1/6): naming the mate is the
  better bet from the start, so every working learner should coordinate. An exact
  check: own side, the mate, $V = 1.1$. A failure points at the partner plumbing or
  at how the mate's choice reaches the reward.
- **8b, stag hunt** (`dso_reward = 0.5`, above 1/6): the DSO pays for sure, mutual
  naming pays more only if both do it. Game theory calls the DSO the risk-dominant
  choice, and independent learners are known to settle on it (Claus and Boutilier,
  1998). CTCE's summed reward makes mutual naming worth $1/3$ to the pair, still
  below 0.5. So 8b is **measured, not judged**: its result is the share of pairs
  that coordinate (`coordinated`). It says how hard the market's version of the
  problem is for each paradigm.

In the market the cost of a failed naming is smaller than in 8b: an order whose
partner does not name it back still goes to the double auction. The market's
partner action therefore has a weaker signal, not a stronger one.

### 9. Conditional part

**Definition.** Observation 0, one step, action `{"side": Discrete(2), "level":
Box(-1, 1)}`; reward $1 - (\text{level} - t_\text{side})^2$ with
$t_\text{sell} = -0.5$ and $t_\text{buy} = +0.5$, plus 0.05 for the agent's own
side ([`ConditionalPartProbe`](../../core/rl/envs/probes.py#L487-L523)).

**Why the market needs it.** The market's best price and quantity depend on the
side: an ask is not a bid. The policy samples them independently of the side, so
while the side is undecided they are one compromise for both sides. The probe
isolates that: the right level depends on the side the policy chose.

**Expected.** Either side, with **its** level: the check leaves the side free
(`None`) and judges the level against the target of the side the policy chose
(`Follows`). The other side at its own level earns 1.0 against 1.05, a near-tie,
so taking it is not a learner fault. $V$ is checked against 1.05, whose tolerance
(0.1575) includes 1.0. A level near 0 is the compromise of an undecided side.

### 10. Long episode

**Definition.** 24 steps, observation $t / 23$ (the hour), reward +1 at the last
step only, the action ignored; trained with $\gamma = 0.95$
([`LongEpisodeProbe`](../../core/rl/envs/probes.py#L525-L555)).

**Why the market needs it.** The market's episode is one day of 24 steps;
probes 1-9 have one or two. The probe checks that discounting and bootstrapping
hold over a day.

**Expected.** $V(t) = 0.95^{23 - t}$, checked at hours 0, 12 and 23 (0.31, 0.57, 1),
each within 15 % of itself (`relative`): an absolute tolerance of 0.15 would
accept anything from 0.16 to 0.46 at hour 0, a value several steps of discounting
off.

---

## Results

The latest full run: 25 October 2026, TalTech job 1048530, `"fast"` preset, seed
0, all 33 combinations on one node in 317 s; the failures again at 2×. The 4×
round was cancelled. The numbers are the largest error over its tolerance (above 1
fails; "miss" is a wrong category); 8b's is the share of pairs that coordinate.

| # | CTCE | CTDE | DTDE |
|---|---|---|---|
| 1-4 | PASS | PASS | PASS |
| 5 | FAIL 1.18 (2×: 1.44) | PASS | PASS |
| 6 | PASS | FAIL 1.73 → **PASS at 2×** | FAIL 1.48 → **PASS at 2×** |
| 7 | FAIL 3.33 (2×: 3.33) | PASS | PASS |
| 8a | PASS | PASS | PASS |
| 8b | 0.50 coordinated | 0.00 | 0.00 |
| 9 | FAIL 2.51 (2×: 1.37) | FAIL 2.59 (2×: 2.42) | FAIL 2.94 (2×: 2.63) |
| 10 | PASS | PASS | PASS |

What they say:

- **The learner works**: probes 1-4 and 10 pass everywhere, 6 passes with twice
  the budget, 8a passes everywhere (the partner plumbing is right).
- **CTCE is slow on probes 5 and 7**, as expected from its summed reward and its
  one joint ratio (L-02); on probe 7 one agent's gate sits at the bound.
- **8b behaves as the theory predicts**: DTDE and CTDE choose the DSO, CTCE
  coordinates one of its two pairs.
- **Probe 9 is the open problem.** In DTDE and CTDE the level's spread collapses
  ($\log \sigma$ down to about −5.5) while its mean is still near 0.1 instead of
  0.5; after that each update's KL grows to 1.5-1.8 and the gradient norm to
  300-380 against a clip of 0.5, so the learner can no longer steer the mean.
  CTCE's spread shrinks more slowly and its level is still moving (0.35 at 30,000
  steps). This is the market's price and quantity under an undecided side; the
  options are in the [RL plan](../plan/rl.md), stage 3.
