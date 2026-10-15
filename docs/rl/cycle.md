# One training iteration, from observation to update

> Every calculation in one training iteration, in the order it happens: the
> agents observe, act and collect a batch of steps; the batch is turned into
> targets; the losses are computed and the networks updated; the new weights go
> back to the agents. PPO is followed in full, with the shapes of what flows
> through each step and what the three paradigms (CTCE, CTDE, DTDE) change on the
> way. APPO and SAC follow as differences from it. Steps that repeat (every
> environment step, every minibatch) are written out once, with how often they
> happen. [The training cycle](training.md) is the shorter overview of the same
> material. [Worked examples](examples.md) puts numbers on the parts our own
> code defines.

**Sources.** As in [The training cycle](training.md): RLlib is Ray 2.51.1, read in
its installed source and linked at tag
[`ray-2.51.1`](https://github.com/ray-project/ray/tree/ray-2.51.1/rllib); the
implementation is `core/rl/` in this repository, with the settings of its
[`SETTINGS`](../../core/rl/config.py#L78-L113) (the original's starting values,
[P2] Table 8, without the defective ones), completed with RLlib's defaults. The
step labels (A1 to D3) are kept as they are for the original code
([`15d6715`](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment)),
so a step that `core/rl/` leaves out still has its label; where the original
computes something else, the step says so and links to
[RL layer: what is wrong](../validation/rl.md).

## Notation

| Symbol | Meaning |
|---|---|
| $N$ | number of agents, $i = 1 \dots N$ |
| $d_o$, $d_a$ | size of one agent's observation and action (taken equal for all agents here) |
| $t$ | environment step: all $N$ agents act at once |
| $o_{i,t} \in \mathbb{R}^{d_o}$ | agent $i$'s observation |
| $s_t = (o_{1,t}, \dots, o_{N,t}) \in \mathbb{R}^{N d_o}$ | all observations, concatenated: CTCE's input, CTDE's global state |
| $x_{i,t} = (o_{i,t}, s_t) \in \mathbb{R}^{(N+1) d_o}$ | agent $i$'s module input in CTDE |
| $u_{i,t} \in \mathbb{R}^{d_a}$ | the action as the policy sampled it, before any rescaling |
| $a_{i,t}$ | the action the environment receives |
| $r_{i,t}$, $R_t = \sum_i r_{i,t}$ | agent $i$'s reward; the group reward of CTCE |
| $m$, $\ell = \log\sigma$ | the Gaussian's mean and log standard deviation, one per action dimension |
| $\pi_\theta$, $\mu$ | the policy being trained; the copy that collected the data |
| $V_\phi$ | the critic (state value) |
| $T$ | environment steps per iteration: 4000 for PPO (RLlib's `train_batch_size`) |
| $K$ | number of env runners (`num_env_runners`, 0 by default: the driver samples) |

Settings used below (PPO): $\gamma = 0.99$, $\lambda = 0.95$, clip $\epsilon = 0.2$,
value coefficient $c_v = 1$, value-loss cap $10^6$, entropy coefficient
$c_H = 0.01$, no KL term, gradient-norm clip 0.5, learning rate $10^{-5}$,
30 epochs, minibatches of 128. An experiment can override them; the market runs use
a learning rate of $3 \cdot 10^{-4}$, batches of 2400 steps, minibatches of 240 and
10 epochs, so C is ≈ 100 gradient steps there instead of ≈ 940.

## Overview

```mermaid
flowchart TD
    subgraph A["A. Collect (env runners), T = 4000 times"]
        A1["A1 observe o"] --> A2["A2 actor forward: m, log σ"]
        A2 --> A3["A3 sample u, log μ(u)"]
        A3 --> A4["A4 rescale u to the bounds: a"]
        A4 --> A5["A5 env step: r, next o, done"]
        A5 --> A1
    end
    subgraph B["B. Targets (learner), once"]
        B1["B1 episodes to batch"] --> B2["B2 add a bootstrap step"]
        B2 --> B3["B3 critic forward: V(o)"]
        B3 --> B4["B4 λ-returns G"]
        B4 --> B5["B5 advantages Â, standardised"]
    end
    subgraph C["C. Update (learner), ≈ 940 times"]
        C1["C1 forward: m', log σ', V"] --> C2["C2 ratio ρ"]
        C2 --> C3["C3-C7 losses"]
        C3 --> C4["C8 gradients"]
        C4 --> C5["C9 clip norm, C10 Adam step"]
    end
    subgraph D["D. After the update, once"]
        D2["D2 weights to env runners"]
    end
    A --> B --> C --> D --> A
```

What happens how often in one PPO iteration:

| Step | How often | Done by |
|---|---|---|
| A1-A5: observe, act, step the environment | $T = 4000$ environment steps, $4000/K$ per env runner when $K > 0$ | env runners (or the driver), with $\mu$ |
| A2: actor forward pass | 4000 per network: $N \times 4000$ in CTDE and DTDE (one per agent's network), 4000 in CTCE | env runners |
| B1-B5: value predictions, returns, advantages | once, over the whole batch, per module | learner, critic before the update |
| C1-C10: one gradient step | 30 epochs × ≈ 31 minibatches ≈ 940; every step used 30 times | learner |
| D2: weights to the env runners | once | learner → env runners |

## A. Collect: from observation to environment step

Each env runner holds a copy $\mu$ of the policy, identical to $\pi_\theta$ at the
start of the iteration (D2 of the previous one). Per environment step it does A1 to
A5. Nothing is learned here: no gradients, no critic.

### A1. Observe

The environment returns one observation per agent, $o_{i,t} \in \mathbb{R}^{d_o}$;
the paradigm's wrapper decides what each module receives
([`env_spec`](../../core/rl/config.py#L116-L126)).

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| What the module receives | $s_t$, all observations joined in the environment's agent order, one input for the group ([`GroupedEnv`](../../core/rl/grouping.py#L68-L137)) | $x_{i,t} = (o_{i,t}, s_t)$, agent $i$'s module ([`CentralStateEnv`](../../core/rl/grouping.py#L147-L194)) | $o_{i,t}$, each agent's module its own |

RLlib passes the observation to the network **as it comes**: the default pipeline
adds a batch dimension and converts to a tensor, but does not normalise (no
`MeanStdFilter`). The market environment scales its features itself, to about
$[-1, 1]$.

### A2. Actor forward pass

The network turns its input into the parameters of a Gaussian: a mean $m$ and a log
standard deviation $\ell = \log\sigma$ per action dimension
([`forward_exploration`](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/core/rl_module/rl_module.py),
which all three modules route to their inference pass). Every paradigm uses
RLlib's default PPO module (`fcnet_hiddens = [256, 256]`, `tanh`), with the actor's
and the critic's encoders separate (`vf_share_layers=False`). The actor:

$$h = \tanh\big(W_2 \tanh(W_1 z + b_1) + b_2\big) \in \mathbb{R}^{256}, \qquad [m, \ell] = W_\pi h + b_\pi, \qquad \ell \leftarrow \text{clip}(\ell, -20, 20),$$

where the input $z$ and the output size are

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| $z$ | $s_t \in \mathbb{R}^{N d_o}$ | the first $d_o$ entries of $x_{i,t}$, i.e. $o_{i,t}$ ([`own_encoder`](../../core/rl/ctde_modules.py#L60-L79)) | $o_{i,t}$ |
| $[m, \ell]$ | $\mathbb{R}^{2 N d_a}$: every agent's mean and log-std from one network | $\mathbb{R}^{2 d_a}$, agent $i$'s network | $\mathbb{R}^{2 d_a}$, agent $i$'s network |

So CTDE's actor is the same network as DTDE's: it never sees the global state.

The value $V_\phi$ is not computed while collecting; PPO needs it only in B3.

**The original** used custom networks in CTCE and CTDE (2 × 128 ReLU, no clip on
$\ell$, [R-03](../validation/rl.md#r-03-the-paradigms-train-different-networks),
[R-01](../validation/rl.md#r-01-the-ctce-and-ctde-action-spread-has-no-limit)), and
in CTDE acted with per-agent heads that were never trained
([I-48](../validation/rl.md#i-48-ctde-never-trains-the-policies-that-act)).

### A3. Sample the action and its log-probability

Per action dimension $k$, with $\sigma_k = e^{\ell_k}$ and fresh noise
$\varepsilon_k \sim \mathcal{N}(0, 1)$
([`get_actions.py`](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/connectors/module_to_env/get_actions.py)):

$$u_k = m_k + \sigma_k \varepsilon_k, \qquad \log\mu(u) = \sum_k \left[-\frac{(u_k - m_k)^2}{2\sigma_k^2} - \ell_k - \tfrac12 \log 2\pi\right].$$

In CTCE the sum runs over all $N d_a$ dimensions, so the group's log-probability is
the sum of the agents': $\log\mu(\mathbf{u}) = \sum_i \log\mu(u_i)$. In CTDE and
DTDE each module samples and scores only its own agent's $d_a$ dimensions.

**Stored for the learner**, per step: the module's input, the sampled $u$,
$\log\mu(u)$, and the distribution's inputs $[m, \ell]$.

### A4. Rescale to the action bounds

The policy's actions are meant to live in $[-1, 1]$; RLlib rescales them to the
environment's bounds and clips (`normalize_actions=True`,
[`space_utils.py` L469-L481](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/utils/spaces/space_utils.py#L469-L481)):

$$a_k = \text{clip}\left(\text{low}_k + (u_k + 1)\,\frac{\text{high}_k - \text{low}_k}{2},\ \text{low}_k,\ \text{high}_k\right).$$

The environment gets $a$; the batch keeps the unclipped $u$. So every $u_k$ beyond
$\pm 1$ acts as the bound, while the learner still sees and trains on the exact
$u_k$. Every agent's dimensions are rescaled with its own bounds: in CTDE and DTDE
its module's own space, in CTCE its slice of the joined space, which keeps the
agents in the environment's order. The original put the grouped bounds in sorted
name order, so a slice could carry another agent's bounds
([I-59](../validation/rl.md#i-59-grouped-spaces-are-in-name-order-grouped-data-in-environment-order)).

### A5. Environment step

The environment applies all $N$ actions at once and returns, per agent, the reward
$r_{i,t}$, the next observation $o_{i,t+1}$ and whether the episode ended
(terminated, or truncated by a time limit).

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Reward stored | $R_t = \sum_i r_{i,t}$ ([`GroupedEnv`](../../core/rl/grouping.py#L122)) | $r_{i,t}$ in agent $i$'s episode | $r_{i,t}$ in agent $i$'s episode |
| Done flag | one, `__all__` | per agent, and `__all__` | per agent, and `__all__` |

The original trained CTDE, like CTCE, on $R_t$.

### A6. Until the batch is full

A1-A5 repeat until 4000 environment steps are collected (`train_batch_size`),
about $4000/K$ per env runner. An episode that is still running when the batch is
full is cut there (`batch_mode="truncate_episodes"`) and continues in the next
iteration, with the next iteration's weights. A cut episode is bootstrapped with
the critic in B2.

## B. Targets: what the loss will be compared with

Once per iteration, on the learner, before any weight changes
([`ppo_learner.py` L60-L80](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/ppo/ppo_learner.py#L60-L80)).

### B1. Episodes to a batch

The collected episode pieces are laid out as one table per RLlib module.

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Modules | 1 | $N$ | $N$ |
| Rows per module | 4000 | ≈ 4000 (one per step the agent acted) | ≈ 4000 |
| One row holds | $s_t$, $\mathbf{u}_t \in \mathbb{R}^{N d_a}$, $R_t$, $\log\mu(\mathbf{u}_t)$, $[m, \ell]$ | $x_{i,t}$, $u_{i,t}$, $r_{i,t}$, $\log\mu(u_{i,t})$, $[m, \ell]$ | $o_{i,t}$, $u_{i,t}$, $r_{i,t}$, $\log\mu(u_{i,t})$, $[m, \ell]$ |

### B2. Add a bootstrap step

Each episode piece gets one artificial step at its end: the last observation
repeated, reward 0, and *truncated* set if the episode did not terminate
([`add_one_ts_to_episodes_and_truncate.py`](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/connectors/learner/add_one_ts_to_episodes_and_truncate.py)).
It exists only so that B3 computes $V_\phi$ of the last observation; a loss mask
removes it from every loss in C.

### B3. Critic forward pass

The critic, with its weights from *before* this iteration's update, evaluates every
row. It has its own encoder (2 × 256 tanh) and a linear value head:

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Value | $V_\phi(s_t)$ | $V_{\phi_i}(x_{i,t}) = V_{\phi_i}(o_{i,t}, s_t)$: agent $i$'s critic sees every agent's observation | $V_{\phi_i}(o_{i,t})$ |

Since the actor and the critic share no layers, the value loss trains only the
critic (C8). In the original, CTCE's and CTDE's critic was a head on the actor's
encoder, and RLlib's default (`vf_share_layers=True`) did the same in DTDE.

### B4. λ-returns

Backwards in time over each episode piece, with $\bar V_{t} = V_\phi(o_t)$, or 0 if
$o_t$ ends a terminated episode
([`value_predictions.py` L7-L38](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/utils/postprocessing/value_predictions.py#L7-L38)):

$$G_t = r_t + \gamma \left[(1 - \lambda)\, \bar V_{t+1} + \lambda\, G_{t+1}\right], \qquad \text{starting from } G = \bar V \text{ at the bootstrap step.}$$

A cut episode therefore ends on the critic's estimate, a terminated one on 0.
Written with the one-step error $\delta_t = r_t + \gamma \bar V_{t+1} - V_\phi(o_t)$,
this is the GAE sum: $G_t = V_\phi(o_t) + \sum_{l \ge 0} (\gamma\lambda)^l \delta_{t+l}$.
$\lambda = 0.95$ sets how far real rewards are used before the critic's estimate
takes over (about $1/(1 - \gamma\lambda) \approx 17$ steps).

$G_t$ is the **value target**. It is not rescaled, so it is on the scale of the
module's reward: in CTCE the summed reward, about $N$ times one agent's; in CTDE and
DTDE the agent's own.

### B5. Advantages

$$\hat A_t = G_t - V_\phi(o_t), \qquad \hat A_t \leftarrow \frac{\hat A_t - \operatorname{mean}(\hat A)}{\max\big(10^{-4}, \operatorname{std}(\hat A)\big)},$$

the mean and standard deviation taken over the module's whole batch
([`general_advantage_estimation.py` L144-L150](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/connectors/learner/general_advantage_estimation.py#L144-L150)).
$\hat A_t > 0$ means "the action taken at $t$ did better than the critic expected".
After standardising, about half of the actions in the batch are reinforced and half
discouraged, whatever the reward scale.

In CTCE there is **one advantage per step for the whole group**: every agent's
action at $t$ is pushed in the same direction by the summed outcome, however much
that agent contributed to it. In CTDE and DTDE each agent has its own advantage,
from its own reward; in CTDE its critic sees the whole state, so the advantage can
discount what the other agents' situation explains.

## C. Update: one gradient step, repeated ≈ 940 times

The 4000 rows of a module are shuffled and cut into minibatches of 128; one pass
over all of them is an epoch; there are 30 epochs, so ≈ 31 × 30 ≈ 940 gradient
steps, and every row is used 30 times
([`ppo.py` L389-L458](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/ppo/ppo.py#L389-L458)).
In CTDE and DTDE each step updates all $N$ modules, each on 128 rows of its own
agent. One gradient step, on a minibatch $b$:

### C1. Forward pass with the current weights

The same networks as in A2 and B3, now with the weights as they are at this step:
$[m', \ell'] = \pi_\theta(\cdot)$ and $V_\phi(\cdot)$ for the 128 rows. In CTDE the
actor is agent $i$'s own network on $o_{i,t}$, the same one that sampled the action
in A2. In the original it was a central actor, not the heads that had acted
([I-48](../validation/rl.md#i-48-ctde-never-trains-the-policies-that-act)).

### C2. Probability ratio

$$\rho_t = \exp\big(\log\pi_\theta(u_t \mid o_t) - \log\mu(u_t \mid o_t)\big),$$

with $\log\pi_\theta$ computed as in A3 but with $m', \ell'$, and $\log\mu$ the value
stored in A3. $\rho_t > 1$: the current policy makes the stored action more likely
than the collecting policy did. On the very first minibatch $\pi_\theta = \mu$, so
$\rho_t = 1$ exactly; that is a check that the stored and recomputed log-probabilities
agree.

In CTCE, $\log\pi_\theta$ is a sum over agents, so $\rho_t = \prod_i \rho_{i,t}$:
one ratio for the joint action. In CTDE and DTDE each agent has its own ratio
$\rho_{i,t}$.

### C3. Clipped surrogate

$$S_t = \min\big(\rho_t \hat A_t,\ \text{clip}(\rho_t, 0.8, 1.2)\, \hat A_t\big).$$

Its gradient is $\hat A_t \rho_t \nabla_\theta \log\pi_\theta(u_t \mid o_t)$ while the
policy has not yet moved more than 20 % on this action in the direction $\hat A_t$
asks for, and **zero** once it has: a good action ($\hat A > 0$) stops being pushed
when $\rho > 1.2$, a bad one when $\rho < 0.8$. This is what keeps 30 epochs on the
same data from running away. In CTCE the clip acts on the joint ratio, so several
agents that each moved a little can together leave the band; in CTDE and DTDE each
agent's ratio is clipped on its own
([worked example](examples.md#5-ctde-in-the-update-per-agent-ratios-and-clips-c2-c3-c8)).

### C4. Value loss

$$L_{V,t} = \min\big((V_\phi(o_t) - G_t)^2,\ 10^6\big).$$

Its gradient is $2 (V_\phi(o_t) - G_t)\, \nabla_\phi V_\phi(o_t)$. The cap
(`vf_clip_param`) is raised from RLlib's 10, which gives **zero** gradient for an
error above $\sqrt{10} \approx 3.2$; the environment scales rewards to returns of
order 1-10, so errors of that size are normal early in training.

### C5. Entropy

$$\mathcal{H}_t = \sum_k \left(\ell'_k + \tfrac12 \log 2\pi e\right).$$

Its gradient with respect to each $\ell'_k$ is exactly 1: with coefficient 0.01 it is
a constant push to widen every action dimension. $\ell$ is clipped to $[-20, 20]$
(A2), so where the reward does not depend on the action the spread grows only to
that bound. In the original's CTCE and CTDE $\ell$ was unclipped and could grow
until it overflowed
([R-01](../validation/rl.md#r-01-the-ctce-and-ctde-action-spread-has-no-limit)).

### C6. KL between the collecting and the current policy

Not computed: `use_kl_loss=False`. The original kept the KL term on with
coefficient $\beta = 0$, so it computed
$\mathrm{KL}_t(\mu \,\|\, \pi_\theta) = \sum_k \big[\ell'_k - \ell_k + \frac{e^{2\ell_k} + (m_k - m'_k)^2}{2\, e^{2\ell'_k}} - \frac12\big]$
for every row, and an infinite KL turned $\beta \cdot \mathrm{KL}$ into NaN
([R-02](../validation/rl.md#r-02-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed)).

### C7. Total loss

Averaged over the minibatch's real rows (the bootstrap rows of B2 masked out):

$$L = \frac{1}{|b|} \sum_{t \in b} \Big[-S_t + 1 \cdot L_{V,t} - 0.01\, \mathcal{H}_t\Big].$$

### C8. Gradients: where each term goes

Backpropagation gives $\partial L / \partial w$ for every weight $w$ the loss
depends on.

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Surrogate and entropy | the actor (encoder and head), from the group's rows | agent $i$'s actor, from agent $i$'s rows only | agent $i$'s actor, from agent $i$'s rows only |
| Value loss | the critic (encoder and head) | agent $i$'s central critic | agent $i$'s critic |
| Networks with no gradient | – | – | – |

The actor and the critic are trained by separate terms, so a large value loss does
not overwrite what the actor's layers learn. In the original's CTDE the acting
heads received no gradient at all (I-48).

### C9. Clip the gradient norm

All gradients of a module are scaled together so that their global norm is at most
0.5 (`grad_clip`, `grad_clip_by="global_norm"`):

$$g \leftarrow g \cdot \min\left(1, \frac{0.5}{\lVert g \rVert_2}\right).$$

The direction is kept, the length capped. If $g$ contains NaN, RLlib replaces it
with zeros, logs a warning and carries on; the trainer stops the run instead, as
soon as a loss or metric is NaN or infinite
([`train.py`](../../core/rl/train.py#L199-L214)).

### C10. Adam step

One optimiser per module (torch's Adam, $\beta_1 = 0.9$, $\beta_2 = 0.999$),
learning rate $\eta = 10^{-5}$, for every weight $w$:

$$m_w \leftarrow 0.9\, m_w + 0.1\, g_w, \qquad v_w \leftarrow 0.999\, v_w + 0.001\, g_w^2, \qquad w \leftarrow w - \eta\, \frac{\hat m_w}{\sqrt{\hat v_w} + 10^{-8}},$$

with $\hat m_w, \hat v_w$ the bias-corrected averages. Adam divides by the gradient's
running size, so each weight moves by about $\eta$ per step whatever the loss scale:
after 940 steps, at most about $0.01$.

Then the next minibatch: C1 again, with the weights just updated.

## D. After the update

### D1. KL coefficient

Not used: without the KL term there is no coefficient to adapt. The original
adapted $\beta$ by 1.5 or 0.5 from the measured KL
([`ppo_torch_learner.py` L141-L166](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/ppo/torch/ppo_torch_learner.py#L141-L166));
from $\beta = 0$ it stayed 0.

### D2. Weights to the env runners

The updated weights are copied to every env runner: $\mu \leftarrow \pi_\theta$. The
next iteration starts at A1 with them. The batch is discarded: PPO never uses a step
again after its iteration.

### D3. Between iterations

The trainer ([`train`](../../core/rl/train.py#L238-L338)) records the iteration's
metrics, stops the run on a NaN or infinite learner metric, and evaluates the
policy and the baselines when the budget of environment steps reaches the next
evaluation point. Hyperparameters stay fixed during a run. In the original,
population-based training could replace a trial's weights with a better trial's and
resample its learning rate, entropy coefficient and $\lambda$
([I-49](../validation/rl.md#i-49-population-based-training-jumps-the-learning-rate-and-reaches-entropy-10)).

## APPO: the same cycle, what changes

Asynchronous PPO: the env runners do not wait for the learner, so the data is a
little older than the policy, and V-trace corrects for it
([`appo_torch_learner.py` L44-L214](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/appo/torch/appo_torch_learner.py#L44-L214)).

| Stage | What changes from PPO |
|---|---|
| A. Collect | A1-A5 are the same. The env runners never stop: they send pieces of 50 steps to the learner as they fill and keep acting, so $\mu$ can be a few updates behind $\pi_\theta$. |
| B. Targets | No GAE, no standardisation. The pieces are gathered into batches of 500 steps, kept in a circular buffer of 4 batches; each batch is trained on at most twice. Targets are computed inside the loss (C), with the current critic. |
| C. Update | One gradient step per 500-step batch. In it: (1) $V_\phi$ for every step; (2) truncated weights $\rho_t = c_t = \min(1, \bar\pi(u_t \mid o_t) / \mu(u_t \mid o_t))$ against a **target policy** $\bar\pi$; (3) V-trace targets backwards in time, $v_t = V_\phi(o_t) + \rho_t \delta_t + \gamma (1 - d_t) c_t (v_{t+1} - V_\phi(o_{t+1}))$; (4) advantage $A_t = \rho_t (r_t + \gamma (1 - d_t) v_{t+1} - V_\phi(o_t))$; (5) the clipped surrogate on $\pi_\theta / \bar\pi$ with clip 0.4, value loss $0.5 \cdot \frac12 (V_\phi - v_t)^2$ (no cap), entropy 0.01, no KL term; (6) gradient-norm clip 0.5, Adam step, learning rate $10^{-5}$. There is no λ, so none is set; the original's `lambda_` had no effect ([R-06](../validation/rl.md#r-06-appos-lambda_-has-no-effect)). |
| D. After | The target policy is overwritten with $\pi_\theta$ every 8000 trained steps. New weights go to the env runners while they keep sampling. An iteration ends after one training step (`min_time_s_per_iteration=0`); the original waited at least 10 s, so its steps per iteration depended on the machine. |

The paradigm differences of A1, A2, B3, B5 and C8 hold as for PPO: in CTDE each
agent's module has its own V-trace on its own reward with its central critic.

## SAC: the same cycle, what changes

Off-policy: steps go into a replay buffer and are trained on later, in random
batches
([`sac_torch_learner.py` L270-L350](https://github.com/ray-project/ray/blob/ray-2.51.1/rllib/algorithms/sac/torch/sac_torch_learner.py#L270-L350)).
SAC learns two critics $Q_{\psi_1}, Q_{\psi_2}$ of state *and action*, their slowly
following copies $\bar Q_1, \bar Q_2$, the actor, and a temperature $\alpha$; in
CTDE and DTDE each agent's module has its own.

| Stage | What changes from PPO |
|---|---|
| A. Collect | A1-A3 as in PPO, but every paradigm uses RLlib's SAC module, which squashes the sample, $\tanh(u) \in (-1, 1)$, before A4's rescaling. Steps are collected in episode fragments (RLlib's default), about 256 environment steps per gradient step, and each step $(o, a, r, o', d)$ goes into a buffer of 1000 steps, the oldest dropped first. Training starts after 1500 steps. The original's CTCE and CTDE used the plain Gaussian of A3, clipped in A4 ([R-04](../validation/rl.md#r-04-sac-in-ctce-and-ctde-uses-an-unsquashed-gaussian)), and collected whole episodes. |
| B. Targets | A random batch of 256 steps from the buffer, old and new. For each: a next action $a' \sim \pi_\theta(\cdot \mid o')$ and the target $y = r + \gamma (1 - d)[\min_j \bar Q_j(o', a') - \alpha \log\pi_\theta(a' \mid o')]$. In the original's CTCE and CTDE, $a'$ came from a target copy of the actor instead. |
| C. Update | Three losses on the same batch, each with its own Adam optimiser: critics $L_Q = \sum_j \text{Huber}(Q_{\psi_j}(o, a) - y)$, learning rate $10^{-5}$; actor $L_\pi = \alpha \log\pi_\theta(\tilde a \mid o) - \min_j Q_{\psi_j}(o, \tilde a)$ with a reparameterised $\tilde a = \tanh(m + \sigma\varepsilon)$, so the actor's gradient runs through $\partial Q / \partial \tilde a$, learning rate $10^{-5}$; temperature $L_\alpha = -\log\alpha\, (\log\pi_\theta(\tilde a \mid o) + \bar{\mathcal{H}})$ with target $\bar{\mathcal{H}} = -\dim A$ (`"auto"`), learning rate $3 \cdot 10^{-4}$. In the original's CTCE and CTDE, $\tilde a$ was drawn with `sample()`, so the actor got no gradient from the critic ([R-05](../validation/rl.md#r-05-sacs-actor-in-ctce-and-ctde-gets-no-gradient-from-the-critic)). |
| D. After | After every gradient step the critic copies follow: $\bar\psi_j \leftarrow 0.005\, \psi_j + 0.995\, \bar\psi_j$. Weights go to the env runners; the buffer is kept, so a step is trained on about once while it stays in the 1000-step buffer. |

| | CTCE | CTDE | DTDE |
|---|---|---|---|
| Critic | $Q_\psi(s, \mathbf{a})$ on all observations and actions | $Q_{\psi_i}(o_i, s, a_i)$: the global state and the agent's own action, not the other agents' actions | $Q_{\psi_i}(o_i, a_i)$ per agent |
| Entropy target $\bar{\mathcal{H}}$ and temperature | $-N d_a$, one $\alpha$ | $-d_a$, one $\alpha_i$ per agent | $-d_a$, one $\alpha_i$ per agent |

## Where the original code departs from this

| Step | What the original does | Recorded as |
|---|---|---|
| A2, C1, C8 | CTDE acts with heads $g_i$ that receive no gradient; the loss trains a central actor | [I-48](../validation/rl.md#i-48-ctde-never-trains-the-policies-that-act) |
| A5, B4, B5 | CTDE learns from the summed reward $R_t$ with one advantage for the group, as CTCE | [I-48](../validation/rl.md#i-48-ctde-never-trains-the-policies-that-act) |
| A2, B3 | CTCE and CTDE: custom 2 × 128 ReLU networks with a shared encoder; DTDE: RLlib's default | [R-03](../validation/rl.md#r-03-the-paradigms-train-different-networks) |
| A2, C5 | CTCE and CTDE: $\ell$ unclipped, so the entropy bonus can grow it until it overflows | [R-01](../validation/rl.md#r-01-the-ctce-and-ctde-action-spread-has-no-limit) |
| A4 | CTCE and CTDE: an agent's slice can be rescaled with another agent's bounds | [I-59](../validation/rl.md#i-59-grouped-spaces-are-in-name-order-grouped-data-in-environment-order) |
| C6, C7, C9 | $\beta = 0$ still computes the KL; an infinite KL makes the loss NaN, and the NaN gradient is zeroed silently | [R-02](../validation/rl.md#r-02-kl_coeff--0-does-not-switch-off-the-kl-term-and-a-nan-loss-goes-unnoticed) |
| D3 | Population-based training raises the learning rate 10-1000× and the entropy coefficient up to 10 | [I-49](../validation/rl.md#i-49-population-based-training-jumps-the-learning-rate-and-reaches-entropy-10) |
| APPO, C | `lambda_` is set and tuned, but V-trace has no λ | [R-06](../validation/rl.md#r-06-appos-lambda_-has-no-effect) |
| SAC, A | CTCE and CTDE: unsquashed Gaussian, clipped | [R-04](../validation/rl.md#r-04-sac-in-ctce-and-ctde-uses-an-unsquashed-gaussian) |
| SAC, C | CTCE and CTDE: the actor's sample is not reparameterised, so no gradient through the critic | [R-05](../validation/rl.md#r-05-sacs-actor-in-ctce-and-ctde-gets-no-gradient-from-the-critic) |
