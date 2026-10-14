# Worked examples: the parts we define

> The training cycle with numbers, limited to what our own code decides: how the
> agents are grouped, how CTDE's per-agent actor is put together, the settings we
> choose, and how a trained policy is evaluated. Everything else (the networks'
> layers, sampling, GAE, the losses, Adam) is RLlib's and is described in
> [One training iteration](cycle.md); it appears here only where our code feeds
> it or reads from it. Step labels (A4, C2, ...) are those of that page.

**The code** is the fixed implementation in `core/rl/` in this repository.
The links point to the local files.
Every number below was computed with that code or with RLlib's own functions
(`unsquash_action`), not by hand.

| File | What it defines | Section here |
|---|---|---|
| [grouping.py](../../core/rl/grouping.py) | `GroupedEnv`: all agents as one, for CTCE and CTDE | 1, 2, 4 |
| [ctde_modules.py](../../core/rl/ctde_modules.py) | CTDE: RLlib's modules with one actor per agent | 3, 5 |
| [config.py](../../core/rl/config.py) | the settings of each of the nine combinations | 6 |
| [policy.py](../../core/rl/policy.py) | acting with a trained policy, baselines, the team score | 7 |
| [train.py](../../core/rl/train.py) | the budget, the NaN stop, when evaluation runs | 8 |

## The example

Three agents, listed by the environment in the order `agent_2, agent_10, agent_1`
(alphabetically `agent_1, agent_10, agent_2`, the case that broke the original,
[I-59](../validation/rl.md#i-59-grouped-spaces-are-in-name-order-grouped-data-in-environment-order)).
Each observes 2 numbers and sets 2 actions: a quantity (kWh, negative = sell) and
a price (€/kWh). The quantity bound is each agent's own capacity.

| Agent | Observation $o_i$ | Quantity bounds | Price bounds |
|---|---|---|---|
| `agent_2` | (0.4, 0.8) | [−5, 5] | [0.05, 0.35] |
| `agent_10` | (−0.2, 0.5) | [−20, 20] | [0.05, 0.35] |
| `agent_1` | (0.9, 0.1) | [−2, 2] | [0.05, 0.35] |

So $N = 3$, $d_o = 2$, $d_a = 2$.

## 1. Grouping the observations (A1, CTCE and CTDE)

[`GroupedEnv`](../../core/rl/grouping.py#L62-L123) turns the three
agents into one agent, `"group"`. Its observation is the agents' observations side
by side, **in the environment's order** (`join`,
[grouping.py L55-L59](../../core/rl/grouping.py#L55-L59)):

$$s = (\underbrace{0.4,\ 0.8}_{\texttt{agent\_2}},\ \underbrace{-0.2,\ 0.5}_{\texttt{agent\_10}},\ \underbrace{0.9,\ 0.1}_{\texttt{agent\_1}}) \in \mathbb{R}^6.$$

The action space is joined the same way (`join_spaces`,
[L28-L34](../../core/rl/grouping.py#L28-L34)), each agent's bounds
in its own slice:

| Position | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Belongs to | `agent_2` q | `agent_2` p | `agent_10` q | `agent_10` p | `agent_1` q | `agent_1` p |
| low | −5 | 0.05 | −20 | 0.05 | −2 | 0.05 |
| high | 5 | 0.35 | 20 | 0.35 | 2 | 0.35 |

To RLlib the group is an ordinary agent with a 6-dimensional `Box` observation and
action. That is the whole point: RLlib's own module and algorithm then train CTCE
without any custom network. In DTDE nothing is grouped: each agent's module gets
its own $o_i$ and its own bounds.

## 2. From the policy's output to the market (A3-A5)

**What RLlib does (A3).** Say the policy outputs, for the 6 dimensions, means and
log-stds

$$m = (0.30,\ -0.10,\ -0.60,\ 0.20,\ 0.10,\ 0.50), \qquad \ell = (-0.50,\ -1.00,\ -0.70,\ -1.20,\ -0.40,\ -0.90),$$

so $\sigma = e^\ell = (0.607, 0.368, 0.497, 0.301, 0.670, 0.407)$, and draws the
noise $\varepsilon = (1.0, -0.5, 0.2, 1.5, -2.0, 0.3)$:

$$u = m + \sigma\varepsilon = (0.907,\ -0.284,\ -0.501,\ 0.652,\ -1.241,\ 0.622).$$

**What our bounds decide (A4).** RLlib rescales each dimension from $[-1, 1]$ to
the joint space's bounds and clips,
$a_k = \text{clip}(\text{low}_k + (u_k + 1)(\text{high}_k - \text{low}_k)/2)$:

| Dimension | $u_k$ | low, high | $a_k$ |
|---|---|---|---|
| `agent_2` q | 0.907 | −5, 5 | −5 + 1.907 × 5 = **4.53** |
| `agent_2` p | −0.284 | 0.05, 0.35 | 0.05 + 0.716 × 0.15 = **0.157** |
| `agent_10` q | −0.501 | −20, 20 | −20 + 0.499 × 20 = **−10.01** |
| `agent_10` p | 0.652 | 0.05, 0.35 | **0.298** |
| `agent_1` q | −1.241 | −2, 2 | −2 + (−0.241) × 2 = −2.48 → clipped to **−2** |
| `agent_1` p | 0.622 | 0.05, 0.35 | **0.293** |

The same $u = -0.501$ would be −2.5 kWh for `agent_2` and −1.0 kWh for `agent_1`:
the bounds must belong to the right agent. The original put the bounds in sorted
name order (`agent_1, agent_10, agent_2`) but the data in this order, so positions
1-2 carried `agent_1`'s bounds and positions 5-6 `agent_2`'s: `agent_2` would have
bid $-2 + 1.907 \times 2 = 1.81$ kWh instead of 4.53, and `agent_1` would have been
clipped at −5 instead of −2, beyond its own capacity (I-59). `agent_10` happens to
sit in the middle of both orders and would have been right.

`agent_1`'s quantity shows the clip: $u = -1.241$ is outside $[-1, 1]$, so the
market gets the bound −2, but the batch keeps $u = -1.241$ and the learner trains
on it.

**Splitting back (A5).** `GroupedEnv.step` cuts the joint action into the agents'
parts (`split`, [L46-L52](../../core/rl/grouping.py#L46-L52)) and
passes them to the environment:

```python
{"agent_2": [4.53, 0.157], "agent_10": [-10.01, 0.298], "agent_1": [-2.0, 0.293]}
```

## 3. CTDE: one actor per agent (A2)

In CTDE each agent's action may depend only on its own observation. Our module
([ctde_modules.py L134-L140](../../core/rl/ctde_modules.py#L134-L140)) is
RLlib's PPO module for the group with the actor replaced by three separate ones,
each the network RLlib would build for that agent alone (`agent_actors`,
[L99-L119](../../core/rl/ctde_modules.py#L99-L119)). The critic is left
as RLlib builds it, on all of $s$.

**Encoders** (`AgentEncoders`,
[L48-L66](../../core/rl/ctde_modules.py#L48-L66)). Agent $i$'s encoder
reads only its slice of $s$: `agent_2`'s positions 1-2 = (0.4, 0.8), `agent_10`'s
3-4 = (−0.2, 0.5), `agent_1`'s 5-6 = (0.9, 0.1). Each turns its 2 numbers into a
256-number latent, $h_i$; the three latents are put side by side (768 numbers).

**Heads** (`AgentHeads`,
[L69-L96](../../core/rl/ctde_modules.py#L69-L96)). Head $i$ reads only
$h_i$ and outputs $[m_{i}, \ell_{i}]$ for its 2 action dimensions. Say:

| Agent | Head output $[m_q, m_p, \ell_q, \ell_p]$ |
|---|---|
| `agent_2` | (0.30, −0.10, −0.50, −1.00) |
| `agent_10` | (−0.60, 0.20, −0.70, −1.20) |
| `agent_1` | (0.10, 0.50, −0.40, −0.90) |

RLlib's Gaussian for a 6-dimensional action reads a 12-number input as *first the 6
means, then the 6 log-stds* (`loc, log_std = logits.chunk(2)`). So the heads'
outputs are **rearranged** before they leave the module:

$$(\underbrace{0.30, -0.10}_{m,\ \texttt{agent\_2}}, \underbrace{-0.60, 0.20}_{m,\ \texttt{agent\_10}}, \underbrace{0.10, 0.50}_{m,\ \texttt{agent\_1}}, \underbrace{-0.50, -1.00}_{\ell,\ \texttt{agent\_2}}, \underbrace{-0.70, -1.20}_{\ell,\ \texttt{agent\_10}}, \underbrace{-0.40, -0.90}_{\ell,\ \texttt{agent\_1}}).$$

These are exactly the $m$ and $\ell$ of section 2, so from here on CTDE is the
same as CTCE: RLlib samples, rescales, stores and trains a 6-dimensional Gaussian.
Had the outputs simply been concatenated, $(0.30, -0.10, -0.50, -1.00, -0.60, 0.20, \dots)$,
RLlib would have read `agent_2`'s log-stds as `agent_10`'s means.

**Sizes** (RLlib's default network, 2 × 256 tanh, actor and critic separate):

| | Actor parameters | Critic parameters |
|---|---|---|
| DTDE, per agent | 67 588 (input 2, output 4) | 66 817 (input 2) |
| CTCE | 70 668 (input 6, output 12) | 67 841 (input 6) |
| CTDE | 3 × 67 588 = 202 764 (three DTDE actors) | 67 841 (CTCE's critic) |

CTDE's actor is the three DTDE actors, and its critic is CTCE's.

## 4. The group's reward (A5, B4)

`GroupedEnv.step` returns one reward for the group, the sum of the agents'
([L104-L123](../../core/rl/grouping.py#L104-L123)). With the market
paying

$$r_{\texttt{agent\_2}} = 1.50, \qquad r_{\texttt{agent\_10}} = -0.50, \qquad r_{\texttt{agent\_1}} = 0.25,$$

the group gets $R = 1.25$. The agents' own rewards travel along in the group's
`infos` (for evaluation), but the learner sees only 1.25.

What follows from it, all computed by RLlib:

- **The critic** $V(s)$ learns the group's return. Its targets are about $N = 3$
  times the size of one agent's, which matters for RLlib's value-loss cap of 10
  ([cycle.md C4](cycle.md#c4-value-loss)).
- **One advantage for the group.** $\hat A$ is computed from $R$, so `agent_1`'s bid
  is reinforced or discouraged by the same number as `agent_2`'s, although here
  `agent_10` lost money and `agent_2` earned it. Telling the agents' contributions
  apart is left to the averaging over many steps (the credit-assignment cost,
  [I-60](../validation/rl.md#i-60-ctce-is-a-centralised-information-baseline-not-an-upper-bound)).

In DTDE each agent's module learns from its own $r_i$ and nothing is summed.

## 5. CTDE in the update: what the per-agent actor means for the loss (C2, C3, C8)

The loss is RLlib's; what our module decides is that the joint policy is a product
of the agents' policies. Here is what that does in numbers.

**Log-probability.** For the stored $u$ of section 2, per dimension
$\log\pi = -\frac{(u - m)^2}{2\sigma^2} - \ell - \frac12\log 2\pi$:

| | `agent_2` | `agent_10` | `agent_1` | Group |
|---|---|---|---|---|
| $\log\mu(u_i)$ when sampled | −0.963 | −1.083 | −2.583 | −4.629 (the sum) |

**Ratio (C2).** Some minibatches later the heads have moved a little: `agent_2`'s
quantity mean 0.30 → 0.36, `agent_10`'s price mean 0.20 → 0.235, `agent_1`'s price
mean 0.50 → 0.53. Recomputed:

| | `agent_2` | `agent_10` | `agent_1` | Group |
|---|---|---|---|---|
| $\log\pi_\theta(u_i)$ | −0.869 | −0.915 | −2.563 | −4.347 |
| $\rho_i = e^{\log\pi_\theta - \log\mu}$ | 1.099 | 1.182 | 1.020 | $\rho = 1.099 \times 1.182 \times 1.020 = $ **1.324** |

**Clip (C3).** RLlib clips the **group's** ratio, $\rho = 1.324$, to $[0.8, 1.2]$.
With $\hat A = +0.8$:

$$S = \min(1.324 \times 0.8,\ 1.2 \times 0.8) = \min(1.060,\ 0.960) = 0.960,$$

the clipped branch: **no gradient for any agent**, although each agent alone
($1.099$, $1.182$, $1.020$) is still inside $[0.8, 1.2]$. Three agents that each
moved a little count as one policy that moved too far. With $\hat A = -0.8$ the
unclipped branch is the smaller one ($-1.060 < -0.960$), so all three keep
receiving gradient. The more agents, the sooner the product leaves the band.
Clipping each agent's ratio separately instead, as MAPPO does, is the open choice
recorded in [training.md](training.md#ctde); the fixed code keeps RLlib's joint
clip.

**Where the gradient goes (C8).** Agent $i$'s network appears only in its own
term of $\log\pi = \sum_i \log\pi_i(u_i \mid o_i)$, so it receives only that term's
gradient. On the first minibatch ($\rho = 1$, unclipped), with $\hat A = +0.8$, the
push on each mean is $\hat A \cdot \partial\log\pi / \partial m_k = \hat A\,(u_k - m_k)/\sigma_k^2$:

| | `agent_2` q | `agent_2` p | `agent_10` q | `agent_10` p | `agent_1` q | `agent_1` p |
|---|---|---|---|---|---|---|
| $(u_k - m_k)/\sigma_k^2$ | 1.649 | −1.359 | 0.403 | 4.980 | −2.984 | 0.738 |
| × $\hat A = 0.8$ | 1.319 | −1.087 | 0.322 | 3.984 | −2.387 | 0.590 |

Each mean is pulled toward the action that was sampled, in proportion to how far
the noise took it ($\varepsilon_k / \sigma_k$). `agent_10`'s head gets only the two
numbers in its columns, from the gradient of its own 2 outputs, and nothing from
the other agents' actions; that is "decentralised execution" in the loss. In CTCE
the same six numbers arrive, but all at one network that sees $s$.

In the original, these gradients went to a central actor and the acting heads got
none ([I-48](../validation/rl.md#i-48-ctde-never-trains-the-policies-that-act)).

## 6. The settings we choose

[`SETTINGS` and `MODEL`](../../core/rl/config.py#L72-L106), and
what each changes in the cycle:

| Setting | Value | What it does in the cycle |
|---|---|---|
| `lr` | $10^{-5}$ | Adam moves each weight about $10^{-5}$ per step (C10) |
| `gamma`, `lambda_` | 0.99, 0.95 | discount and GAE horizon, ≈ 17 steps (B4) |
| `num_epochs`, `minibatch_size` | 30, 128 | with RLlib's 4000 steps per batch: 30 × ⌈4000/128⌉ ≈ 940 gradient steps per iteration |
| `clip_param` | 0.2 | the band $[0.8, 1.2]$ of section 5 |
| `entropy_coeff` | 0.01 | the constant push to widen $\sigma$ (C5) |
| `grad_clip` | 0.5 | gradient norm capped at 0.5 (C9) |
| `use_kl_loss` | False | the KL term is not computed at all (C6 disappears; fixes [R-02](../validation/rl.md#r-02-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)) |
| `vf_share_layers` | False | actor and critic have separate encoders: the value loss no longer trains the actor's layers (C8) |
| SAC `target_entropy` | `"auto"` | $-\dim A$ of each module: **−2** per agent in DTDE, **−6** for the group in CTCE and CTDE |

**Steps per iteration.** One PPO iteration samples 4000 environment steps. In
CTCE and CTDE that is 4000 rows of the group; in DTDE 4000 rows for *each* of the
three modules, 12 000 rows in total, but still 4000 environment steps. The budget
counts environment steps, so all paradigms get the same amount of experience.

## 7. Evaluating a trained policy

[`Policy`](../../core/rl/policy.py#L54-L131) acts with the trained
module outside RLlib, the same way RLlib does in training, but without noise.

**The action** (`act`, [L96-L111](../../core/rl/policy.py#L96-L111)).
The most likely action is the mean, then RLlib's own rescaling with the joint
bounds, then the split:

| | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| PPO, APPO: $a = \text{rescale}(m)$ | (1.50, 0.185) | (−12.0, 0.230) | (0.20, 0.275) |
| SAC: $a = \text{rescale}(\tanh m)$ | (1.46, 0.185) | (−10.74, 0.230) | (0.199, 0.269) |

For example `agent_10`'s quantity: $-20 + (-0.60 + 1) \times 20 = -12.0$. SAC's
actions are squashed by tanh, so its most likely action is $\tanh m$; RLlib's own
deterministic SAC action skips the tanh in Ray 2.51.1, so `_deterministic`
([L39-L51](../../core/rl/policy.py#L39-L51)) applies it. The
original's inference used the mean without rescaling, so `agent_10` would have bid
−0.60 kWh ([I-61](../validation/rl.md#i-61-standalone-inference-does-not-act-like-training)).

**Baselines** ([L137-L165](../../core/rl/policy.py#L137-L165)).
"Random" draws each action uniformly within its bounds. "Zero" sends 0 in the
market's units, clipped to the bounds: quantity 0, price $\max(0, 0.05) = 0.05$
for every agent. It is *not* the network's 0, which would be the middle of the
bounds (price 0.20).

**The team score** (`Episode`,
[L172-L192](../../core/rl/policy.py#L172-L192)). Every paradigm is
scored in the original multi-agent environment, from the raw per-agent rewards.
Over a 3-step episode:

| Step | `agent_2` | `agent_10` | `agent_1` |
|---|---|---|---|
| 1 | 1.50 | −0.50 | 0.25 |
| 2 | 0.80 | 0.30 | −0.10 |
| 3 | −0.20 | 1.10 | 0.40 |
| **Return** | **2.10** | **0.90** | **0.55** |

Team score $= 2.10 + 0.90 + 0.55 = 3.55$, reported with the three returns. The
same number for CTCE, CTDE and DTDE, computed the same way, so the nine
combinations and the baselines can be ranked on one scale
([I-73](../validation/rl.md#i-73-returns-of-the-paradigms-are-compared-across-different-scales)).
Evaluation episodes use seeds from 1 000 000 on, which training never reaches
(`evaluation_seeds`,
[L245-L249](../../core/rl/policy.py#L245-L249)).

`Policy.values` gives the critic's estimate of a state; in CTCE and CTDE that is
the group's value, comparable to the team score, not to one agent's return.

## 8. The run: budget, NaN stop, evaluation

[`train`](../../core/rl/train.py#L238-L335) repeats RLlib's
iteration until the budget of environment steps is used up.

**Budget.** `budget = 100_000` with PPO's 4000 steps per iteration: 25 iterations,
for every paradigm. With `eval_every = 20_000`, the policy and baselines are
evaluated at 0 (untrained, together with random and zero), 20 000, 40 000, 60 000,
80 000 and at the end, 100 000
([L283-L302](../../core/rl/train.py#L288-L307)).

**NaN stop** (`_nonfinite`,
[L194-L209](../../core/rl/train.py#L199-L214)). After each
iteration the learner's results are searched for losses, entropies and the SAC
temperature that are NaN or infinite. For

```python
{"group": {"policy_loss": nan, "vf_loss": 0.31, "entropy": inf,
           "num_env_steps_trained_throughput": nan}}
```

it finds `group/policy_loss` and `group/entropy` and stops the run with an error,
which `run.json` records. The throughput is skipped on purpose: RLlib reports it
as NaN in the first iteration. The original carried on with zeroed gradients
([R-02](../validation/rl.md#r-02-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)).
