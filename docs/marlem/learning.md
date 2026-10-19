# MARLEM: the learning layer as stated in the papers

> The reinforcement-learning half of the MARLEM method, the counterpart of
> [the market as stated in the paper](methodology.md): what the agents observe and
> do, the three training paradigms, the three algorithms, their hyperparameters,
> population-based training, and the 3 × 3 experiment. Each section says **what
> the papers say**. Where they leave out something needed to run it, a folded
> section titled **In the original code** (click to open) gives how the original
> implementation ([salazarna/marlem](https://github.com/salazarna/marlem/tree/15d6715a7b7ad31700d3758f2a2dd9df053773a7),
> commit `15d6715`) configures it, so every setting has a reference value. Those
> sections describe the code as it is; what is wrong in it is recorded separately,
> in [RL layer: what is wrong](../validation/rl.md), and only linked here.

**Sources**

- **[P1]** Salazar-Peña, Tabares, González-Mancera. *MARLEM: A multi-agent
  reinforcement learning simulation framework for implicit cooperation in
  decentralized local energy markets.* Applied Energy 412 (2026) 127546.
  [doi:10.1016/j.apenergy.2026.127546](https://doi.org/10.1016/j.apenergy.2026.127546). §3.2 (the Dec-POMDP) and §3.7 (paradigms and
  algorithms, in words). [P1] trains nothing; it defers "the full mathematical
  and implementation specifics" of MARL to [P2].
- **[P2]** Same authors. *Harnessing Implicit Cooperation: A Multi-Agent
  Reinforcement Learning Approach Towards Decentralized Local Energy Markets.*
  SSRN preprint 6685504, not peer reviewed. §3.3 (algorithms, eq. 11-15), §3.4
  (paradigms, eq. 16-20), §4 (the case study and training setup, Tables 6-8), §5
  (results, Tables 9-10).
- **The original code**: `src/environment/` (`lem.py`, `action.py`,
  `observation.py`, `train.py`, `ctce.py`, `ctde.py`, `inference.py`) and the
  notebook `notebooks/case6_implicit_cooperation.ipynb`, which sets up [P2]'s
  experiment. It is built on Ray RLlib 2.x (new API stack) and Ray Tune.

Equation numbers are the papers' own and marked with the paper. The reward and the
KPIs are compared paper against paper against code in
[The two papers](../validation/papers.md#3-reward) and are only summarised here.

**Notation**

| Symbol | Meaning |
|---|---|
| $i \in \mathcal{I}$, $I = \lvert\mathcal{I}\rvert$ | agent, number of agents |
| $t \in \{0, \dots, \tau\}$ | trading period (step) of an episode |
| $o_i$, $a_i$, $R_i$ | agent $i$'s observation, action and reward |
| $s$, $\mathbf{a}$ | global state, joint action |
| $\pi_\theta$, $Q_\phi$, $V$ | policy (actor), action-value critic, state-value critic |
| $\psi$ | discount factor ([P2]'s symbol; $\gamma$ in RLlib) |

## 1. The learning problem ([P1] §3.2, [P2] §3.1)

The market is a decentralised partially observable Markov decision process
(Dec-POMDP) $\langle \mathcal{I}, \mathcal{S}, \mathcal{A}, \mathcal{P}, \mathcal{R}, \Omega, \mathcal{O} \rangle$:
each agent $i$ sees only its own observation $o_i$, chooses its own action $a_i$
and receives its own reward $R_i$; the transition $\mathcal{P}(s' \mid s, \mathbf{a})$
is one market step ([methodology §3](methodology.md#3-one-market-step-p1-39-fig-4)).
An episode is one day of $\tau = 24$ hourly steps ([P2] Table 7).

### 1.1 Action ([P1] eq. 2)

$$
a_i = \left\langle p_{\text{bid}},\ q_{\text{bid}},\ \alpha,\ \beta \right\rangle \tag{[P1] 2}
$$

Price, quantity, order type (0 sell, 1 buy) and preferred partner (another agent,
the DSO, or none), as in [methodology §2](methodology.md#2-orders-p1-323). [P1]
calls the action space continuous.

??? note "In the original code"

    `ActionHandler`
    ([action.py L35-L44](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/action.py#L35-L44))
    gives every agent one continuous `Box` of 4 numbers; the discrete parts are
    decoded from it in `step`
    ([lem.py L351-L381](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L351-L381)):

    | Dimension | Bounds | Decoded as |
    |---|---|---|
    | $p_{\text{bid}}$ | [`min_price`, `max_price`] | clipped to the bounds |
    | $q_{\text{bid}}$ | [`min_quantity`, min(`max_quantity`, agent capacity)] | clipped to [`min_quantity`, `max_quantity`] |
    | $\alpha$ | [0, 1] | buy if $> 0.5$ |
    | $\beta$ | [0, $I + 1$] | `int(β)`: $0 \dots I-1$ an agent (in list order), $I$ the DSO, $I + 1$ no preference |

    With `enable_partner_preference=False` the learned $\beta$ is ignored and a
    rule picks the partner. With `enable_asynchronous_order=True` each order's time
    gets a random offset within the step. In [P2]'s case, 8 agents × 4 = 32 action
    numbers for the group.

    The policy outputs a Gaussian over these 4 numbers; RLlib rescales its sample
    from $[-1, 1]$ to the `Box` bounds before `step` sees it.

### 1.2 Observation ([P1] Table 2, [P2] Table 5)

Three blocks, the same 42 signals in both papers (listed in
[The two papers §1](../validation/papers.md#1-dec-pomdp-and-observation)):

| Block | Signals | Visible to |
|---|---|---|
| Market signals | 16: step, time of day, clearing price and volume, grid balance, DSO volumes and prices, P2P volume, local prices | all agents (public) |
| Agent signals | 16: generation and demand (forecasts), demand and supply satisfied and deferred, profit, reputation, battery state | the agent only (private) |
| Implicit-cooperation KPIs | 10: welfare, liquidity, spread, volatility, imbalance, congestion, coordination score and convergence, self-consumption, flexibility use | all agents (shared) |

When partner preference is on, the observation adds every agent's reputation.
The KPIs are the "stigmergic" signals of [P2]: they are what lets independent
learners see the others' aggregate effect (§2, DTDE). Forecasts carry up to 30 %
error ([P2] Table 7).

??? note "In the original code"

    `ObservationHandler`
    ([observation.py L65-L176](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/observation.py#L65-L176))
    builds one `Box` per agent: the 42 signals, plus $I$ reputations when
    `enable_partner_preference=True`, so $42 + 8 = 50$ numbers per agent in [P2]'s
    case and $8 \times 50 = 400$ for the group in CTCE and CTDE. Each signal has its
    own bounds (prices in the market's price range, volumes up to
    `max_quantity` × $I$, the step up to `max_steps`, ...). The values are passed
    to the networks **as they are**: neither the environment nor the trainer
    normalises them.

### 1.3 Reward ([P1] eq. 3-6, [P2] eq. 3)

Every agent gets its own reward each step: a base reward of five weighted parts
(grid balance, resource allocation, trading, stability, economic efficiency),
raised by a cooperation bonus $f_{\text{coop}} \cdot f_{\text{contrib},i}$ built from the
KPIs, minus penalties for DSO reliance and unmet demand. The two papers write the
overall form differently, and the code is a third version; all three, with the
weights, are in [The two papers §3](../validation/papers.md#3-reward).

What matters for training: the reward is **per agent**. How it becomes a
paradigm's learning signal is the paradigm's choice (§2).

### 1.4 Episodes and seeds

[P2]: 24 steps of one hour; a global seed (42) controls "all stochastic processes
within the simulation", so that "environmental conditions are identical across all
experimental runs" (§4.3). DSO price profiles are kept fixed between episodes.

??? note "In the original code"

    - **Episode end**
      ([lem.py L443-L453](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L443-L453)):
      all agents are *terminated* (and `"__all__"` set) once the step counter
      reaches `max_steps − 1`.
    - **Seeding**
      ([lem.py L258-L311](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/lem.py#L258-L311)):
      every `reset` calls `np.random.seed(seed)` with the seed from `env_config`
      (42) unless one is passed, so every episode starts from the same random state.
    - `enable_reset_dso_profiles=False` keeps the DSO prices of the first day.

## 2. Training paradigms ([P1] §3.7.1, [P2] §3.4)

| Paradigm | Training | Execution | Objective |
|---|---|---|---|
| **CTCE** | One policy on the global state $s$ (all observations concatenated) | The same policy outputs the joint action | Sum of all agents' returns, [P2] eq. 17 |
| **CTDE** | Each agent's actor, guided by a centralised critic $Q_\phi(s, \mathbf{a})$ on the global state and joint action | Each actor on its own $o_i$; the critic is dropped | [P2] eq. 18 |
| **DTDE** | Each agent learns alone from its own $o_i$ and $R_i$ | Local | Own return, [P2] eq. 19 |

$$
\pi_\theta(a_1, \dots, a_I \mid s) = \prod_{i=1}^{I} \pi_{\theta,i}(a_i \mid s) \tag{[P2] 16}
$$

$$
J_{\text{CTCE}}(\theta) = \mathbb{E}\left[ \sum_{t=0}^{\tau} \sum_{i=1}^{I} \psi^t R_i(s_t, \mathbf{a}_t) \right] \tag{[P2] 17}
$$

$$
\nabla_{\theta_i} J(\theta_i) = \mathbb{E}\left[ \nabla_{\theta_i} \log \pi_{\theta_i}(a_i \mid o_i)\; Q_\phi(s, a_1, \dots, a_I) \right] \tag{[P2] 18}
$$

$$
J_{\text{DTDE}}(\theta_i) = \mathbb{E}\left[ \sum_{t=0}^{\tau} \psi^t R_i(o_{i,t}, a_{i,t}) \right] \tag{[P2] 19}
$$

$$
P_i(s' \mid s, a_i) = \sum_{a_{-i}} P(s' \mid s, a_i, a_{-i}) \prod_{j \ne i} \pi_j(a_j \mid o_j) \tag{[P2] 20}
$$

Eq. 20 is the non-stationarity an independent learner faces: the others' policies
are part of its environment. The papers' answer is the shared KPIs in the
observation, which make that environment "quasi-stationary". [P1] calls CTCE "a
theoretical upper bound for system performance" and [P2] uses it as the benchmark
the other paradigms are measured against.

??? note "In the original code"

    The paradigm is chosen with `TrainingMode` and set up in
    `_setup_training_config`
    ([train.py L296-L353](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L296-L353)).

    **DTDE.** The market environment as it is, one RLlib policy per agent
    (`policy_mapping_fn` maps agent $i$ to policy $i$), each with **RLlib's
    default module** for the algorithm (`DefaultPPOTorchRLModule`,
    `DefaultAPPOTorchRLModule`, `DefaultSACTorchRLModule`) and default network
    settings. Nothing is shared between agents; each learns from its own reward.

    **CTCE and CTDE: the grouped environment.** `GroupedLEM`
    ([train.py L623-L705](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L623-L705))
    wraps the market with RLlib's `with_agent_groups` into one agent,
    `"grouped_agents"`, whose observation and action are `Tuple`s of the agents'
    and whose reward is the **sum** of the agents' rewards (as [P2] eq. 17). The
    episode ends for the group when it ends for all.

    **CTCE: `CTCEModule`**
    ([ctce.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctce.py#L22-L375)),
    a custom RLlib module, with `embeddings_dim = 128`:

    | Part | Network |
    |---|---|
    | Encoder | all observations concatenated → Linear(128) → ReLU → Linear(128) → ReLU |
    | Actor head `pi` | Linear(128 → 2 × all action dims): a mean and a log-std per action number |
    | Critic head `vf_head` | Linear(128 → 1), on the same encoder |
    | SAC only | twin Q encoders (same shape) on observations and actions, each with a Linear(128 → 1) head; target copies of actor and critics |
    | Distribution | one diagonal Gaussian per agent (`TorchDiagGaussian`), combined |

    **CTDE: `CTDEModule`**
    ([ctde.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/ctde.py#L22-L383)):
    the same central encoder, actor head and critic head as CTCE, plus one network
    per agent, `pi_heads[i]`: $o_i$ → Linear(128) → ReLU → Linear(128) → ReLU →
    Linear(2 × $\dim a_i$). Acting (data collection, evaluation, inference) uses
    `pi_heads`, each on its own agent's observation; the loss is computed from the
    central `pi`. That split is the defect
    [L-01](../validation/rl.md#l-01-ctde-never-trains-the-policies-that-act).

## 3. Algorithms ([P1] §3.7.2, [P2] §3.3)

All three are actor-critic methods for continuous actions:

**PPO**, on-policy: a clipped surrogate objective with GAE advantages.

$$
J^{\text{CLIP}}(\theta_i) = \mathbb{E}_t\left[ \min\left( r_t(\theta_i) A_t,\ \operatorname{clip}\left(r_t(\theta_i), 1 - \varepsilon, 1 + \varepsilon\right) A_t \right) \right], \qquad r_t(\theta_i) = \frac{\pi_{\theta_i}(a_t \mid o_t)}{\pi_{\theta_{\text{old}}}(a_t \mid o_t)} \tag{[P2] 11-12}
$$

**APPO**, asynchronous PPO: actors sample while the learner trains, and V-trace
corrects for the lag between the two.

$$
V_t^{\text{target}} = V(s_t) + \sum_{k=0}^{l-1} \psi^k \left( \prod_{j=0}^{k-1} c_{t+j} \right) \rho_{t+k}\, \delta_{t+k}, \qquad \rho_t = \min\left( \bar\rho,\ \frac{\pi_{\text{target}}(a_t \mid o_t)}{\pi_{\text{behavior}}(a_t \mid o_t)} \right) \tag{[P2] 13-14}
$$

**SAC**, off-policy with a replay buffer: maximises reward plus entropy, with twin
Q-networks and a learned temperature $\alpha$.

$$
J(\pi) = \sum_{t=0}^{\tau} \mathbb{E}_{(o_t, a_t) \sim \rho_\pi}\left[ r(o_t, a_t) + \alpha\, \mathcal{H}\left(\pi(\cdot \mid o_t)\right) \right] \tag{[P2] 15}
$$

How each is computed step by step in RLlib is in
[One training iteration](../rl/cycle.md).

??? note "In the original code"

    `RLAlgorithm` selects RLlib's `PPOConfig`, `APPOConfig` or `SACConfig`
    ([train.py L207-L262](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L207-L262)),
    with PyTorch, one learner, and RLlib's new API stack. Everything the code does
    not set is RLlib's default (§4).

## 4. Hyperparameters ([P2] Table 8)

[P2] gives the **initial** values; population-based training changes some of them
during training (§5).

| | PPO | APPO | SAC |
|---|---|---|---|
| Learning rate | $10^{-5}$ | $10^{-5}$ | actor $10^{-5}$, critic $10^{-5}$ |
| Discount $\psi$ | 0.99 | 0.99 | 0.99 |
| Entropy coefficient | 0.01 | 0.01 | dynamic (target entropy\*) |
| Gradient clip | 0.5 | 0.5 | 0.5 |
| Clip parameter | 0.2 | – | – |
| Advantage | GAE | V-trace | – |
| Batch / buffer | minibatch 128 | – | buffer capacity 1000 |

\* "For centralized paradigms (CTCE/CTDE), the target entropy is set to the
negative sum of all action dimensions ($-\sum \dim A_i$). For the decentralized mode
(DTDE), it corresponds to the negative dimension of the individual agent's action
space ($-\dim A_i$)."

??? note "In the original code"

    **What the code sets**
    ([train.py L215-L259](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L215-L259)),
    Table 8's values plus the ones [P2] does not list:

    | Setting | PPO | APPO | SAC |
    |---|---|---|---|
    | `lr` | 1e-5 | 1e-5 | `actor_lr` 1e-5, `critic_lr` 1e-5 |
    | `gamma` | 0.99 | RLlib default 0.99 | 0.99 |
    | `lambda_` | 0.95 | 0.95 | – |
    | `use_critic`, `use_gae` | True, True | – | – |
    | `vtrace` | – | True | – |
    | `num_epochs` | 30 | – | – |
    | `minibatch_size` | 128 | – | – |
    | `kl_coeff` | 0.0 | 0.0 | – |
    | `entropy_coeff` | 0.01 | 0.01 | – |
    | `clip_param` | 0.2 | RLlib default 0.4 | – |
    | `grad_clip` | 0.5 | 0.5 | 0.5 |
    | `twin_q` | – | – | True |
    | `target_entropy` | – | – | $-\sum_i \dim a_i$ (CTCE, CTDE), $-\dim a_i$ of the first agent (DTDE) |
    | Replay buffer | – | – | `EpisodeReplayBuffer` (CTCE, CTDE) or `MultiAgentEpisodeReplayBuffer` (DTDE), capacity 1000 |
    | `batch_mode` | RLlib default `truncate_episodes` | default | `complete_episodes` |

    With [P2]'s 4 action numbers per agent and 8 agents, SAC's target entropy is
    −32 for the group and −4 per agent.

    **What comes from RLlib's defaults** (Ray 2.51.1), which the code does not set:

    | | PPO | APPO | SAC |
    |---|---|---|---|
    | Batch per iteration | 4000 environment steps (`train_batch_size`) | fragments of 50 steps, learner batches of 500 | 256 transitions per gradient step |
    | Updates | 30 epochs × minibatches of 128, ≈ 940 per iteration | one per batch, each batch reused up to twice | one per training step; starts after 1500 sampled steps |
    | Value loss | coefficient 1.0, squared error capped at 10 | coefficient 0.5 | Huber loss on the twin Q-values |
    | Other | `use_kl_loss=True`, `kl_target` 0.01 | target policy refreshed every 2 × 4 × 2 batches, circular buffer of 4 batches | `tau` 0.005, initial $\alpha$ 1.0, $\alpha$ learning rate 3e-4 |
    | Iteration length | one training step | at least 10 s | at least 1 s and 100 sampled steps |
    | Actions | rescaled from $[-1, 1]$ to the bounds (`normalize_actions=True`) | the same | the same |

    **Networks.** The papers do not describe them. In DTDE they are RLlib's
    defaults (for PPO and APPO: two hidden layers of 256, tanh, actor and critic
    on a shared encoder, log-std clipped at ±20); in CTCE and CTDE the custom
    modules of §2 (128, ReLU).

## 5. Population-based training ([P1] §3.7.2, [P2] §4.2)

Both papers name Population-Based Training (PBT, Jaderberg et al. 2017), which
"jointly optimizes the neural network weights and hyperparameters of a population"
([P1]). [P2]: "10 tune samples for each of the nine configurations, resulting in
90 concurrent trials … PBT periodically clones the weights of the best-performing
trials, while … the framework mutates the hyperparameters of low-performing
trials." Which hyperparameters, over which ranges and how often are not given.

??? note "In the original code"

    `RLTrainer.train`
    ([train.py L401-L460](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L401-L460))
    runs every training through Ray Tune with `PopulationBasedTraining`, also for a
    single trial:

    | Setting | Value |
    |---|---|
    | Trials | `tune_samples` (default 1) |
    | Score | `env_runners/episode_return_mean`, maximised |
    | Perturbation interval | every `checkpoint_freq` training iterations |
    | Mutated (PPO, APPO) | `lr` ~ loguniform(1e-4, 1e-2), `entropy_coeff` ~ loguniform(0.01, 10), `lambda_` ~ loguniform(0.8, 0.99) |
    | Mutated (SAC) | `actor_lr`, `critic_lr` ~ loguniform(1e-4, 1e-2) |
    | Exploit, explore | Ray Tune's defaults: the bottom 25 % of trials copy a top-25 % trial's weights and settings; each setting is then resampled from its range with probability 0.25, else multiplied by 1.2 or 0.8 |

    The mutation ranges are in
    [train.py L178-L198](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L178-L198).
    How they relate to the starting values is
    [L-10](../validation/rl.md#l-10-population-based-training-jumps-the-learning-rate-and-reaches-entropy-10).

## 6. The training run ([P2] §4.2)

[P2]: "Each configuration is trained for a total of 10 000 episodes … Model
checkpoints are saved every 10 iterations, and the evaluation is performed at each
training iteration, with the duration automatically determined by the framework
… based on the capacity of the evaluation workers." Hardware: a 12-core Ryzen 9
9900X, 128 GB RAM, an RTX 4090.

??? note "In the original code"

    `RLTrainer`
    ([train.py L39-L460](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/train.py#L39-L460)):

    | Setting | Argument (default) | What it does |
    |---|---|---|
    | Budget | `iters` (100) | training stops after this many **training iterations** |
    | Checkpoints | `checkpoint_freq` (10) | every `checkpoint_freq` iterations and at the end; the 3 best by evaluation return are kept |
    | Evaluation | `evaluation_interval` (1), `evaluation_duration` ("auto") | every iteration, in episodes, in parallel with training, without exploration (`exploration=False`: the policy's most likely action) |
    | Workers | `cpus` (`cpu_count() − 4`) | that many sampling workers and as many evaluation workers |
    | GPUs | `gpus` (all CUDA devices) | for the one learner |
    | Output | `storage_path` | Tune experiment `lem_<algorithm>_<paradigm>_<date>`, plus the environment config |

    `train_checkpoint` continues from a checkpoint; `restore_experiment` resumes a
    Tune experiment.

    **[P2]'s experiment in the notebook.** `case6_implicit_cooperation.ipynb` runs
    one combination at a time (`ALGO`, `MODE`) with:

    | Setting | [P2] | Notebook |
    |---|---|---|
    | Budget | 10 000 episodes | `iters=10000` (`TRAINING_EPISODES`), so 10 000 iterations |
    | Trials | 10 per configuration | `TUNE_SAMPLES = 100` |
    | Checkpoints (and PBT interval) | every 10 iterations | `CHECKPOINT_FREQ = 2` |
    | Evaluation | every iteration, automatic duration | `EVALUATION_INTERVAL = 1`, `EVALUATION_DURATION = 3` |
    | Resources | 12 cores, 1 GPU | `CPUS = 1`, `GPUS = 0` |
    | Network width | – | `EMBEDDINGS_DIM = 128` |

## 7. The 3 × 3 experiment ([P2] §4-5)

**Set-up.** 8 agents on the IEEE 34-bus feeder ([P2] Table 6), each with PV and a
battery (95 % efficiency, SoC 5-95 %):

| Agent | Node | Capacity (kW) | Battery (as printed, kW) |
|---|---|---|---|
| Small industry | 840 | 180 | 108 |
| Community hospital | 890 | 170 | 85 |
| University campus | 844 | 140 | 98 |
| Shopping mall | 816 | 130 | 78 |
| Residential complex | 800 | 80 | 64 |
| Apartment building | 830 | 75 | 52.5 |
| Community solar farm | 848 | 180 | 180 |
| Parking lot | 860 | 160 | 144 |

Environment ([P2] Table 7): 24 steps of 1 h, grid capacity 1800 kW, seed 42,
prices 20-600, quantities 0-180 kWh, forecast error 30 %, asynchronous orders.
Average pricing, $p = (p_{\text{buy}} + p_{\text{sell}})/2$, and partner preference
enabled (§4.1).

??? note "In the original code"

    The notebook builds a different population: 8 agents
    `commercial_morning_001` … `flexible_coordinator_002` of 150-400 kW, battery
    ratios 0.5-1.0 (SoC 5-95 %, efficiency 0.95), profiles from
    `data/*_60min.csv`, on `GridTopology.IEEE34` with 8 nodes, and the
    **proportional-surplus** clearing mechanism. The rest matches Table 7:
    `max_steps=24`, capacity 1800 kW, seed 42, prices 20-600, quantities 0.1-180,
    `max_error=0.3`, `num_anchor=4`, `enable_asynchronous_order=True`,
    `enable_reset_dso_profiles=False`, `enable_partner_preference=True`.

**Results** ([P2] Table 9, mean episode reward over 10 000 training episodes; all
nine runs converged before 300 episodes):

| | CTCE PPO | CTCE APPO | CTCE SAC | CTDE PPO | CTDE APPO | CTDE SAC | DTDE PPO | DTDE APPO | DTDE SAC |
|---|---|---|---|---|---|---|---|---|---|
| Mean | 3099.4 | 3143.9 | 3139.8 | 3004.8 | 3096.5 | 3158.2 | 2742.5 | 2998 | 54.5 |
| Max | 3123.3 | 3272.1 | 3189.7 | 3074.1 | 3181.4 | 3166.1 | 2935.2 | 3243.5 | 708.4 |

**Final hyperparameters after PBT** ([P2] Table 10, best trial of each
configuration):

| | CTCE PPO | CTCE APPO | CTCE SAC | CTDE PPO | CTDE APPO | CTDE SAC | DTDE PPO | DTDE APPO | DTDE SAC |
|---|---|---|---|---|---|---|---|---|---|
| Learning rate | 9.2e-6 | 3.3e-4 | 4.6e-3 | 9.2e-6 | 1.2e-5 | 2.9e-3 | 4.4e-3 | 3.7e-5 | 1.0e-3 |
| Entropy coefficient | 5.72 | 0.01 | – | 0.04 | 0.01 | – | 0.24 | 0.02 | – |

**Scalability test** ([P2] §4.3): the same set-up with 1000 episodes per run, one
PBT trial, the full 3 × 3 matrix, and 2, 20 or 34 agents; wall-clock time to
convergence is measured.

## 8. Using a trained policy

The papers do not describe how a trained policy is run outside training.

??? note "In the original code"

    `RLInference`
    ([inference.py](https://github.com/salazarna/marlem/blob/15d6715a7b7ad31700d3758f2a2dd9df053773a7/src/environment/inference.py))
    loads the module from a checkpoint and plays `iters` episodes (the notebook:
    `ITERS_INFERENCE = 100`). For each agent it takes the network's mean action
    (`exploration=False`) or samples from the Gaussian (`exploration=True`), clips
    it to the action bounds and steps the environment, collecting episode rewards
    and market metrics. DTDE runs on the market environment, CTCE and CTDE on the
    grouped one. How this differs from training's actions is
    [L-15](../validation/rl.md#l-15-standalone-inference-does-not-act-like-training).

## 9. Points the papers leave unspecified

Needed to train MARLEM's agents but not given in [P1] or [P2]:

- The network architectures (layers, sizes, activations, shared or separate actor
  and critic).
- What "10 000 episodes" means in RLlib's terms, and the batch size of PPO and APPO.
- PPO's number of epochs, $\lambda$ and KL settings; APPO's buffer and target
  update; SAC's batch size, warm-up and target-network rate.
- The PBT mutation ranges, perturbation interval and exploit rule.
- How the observation is scaled before it reaches the networks.
- How the action's discrete parts ($\alpha$, $\beta$) come from a continuous policy.
- The number of evaluation episodes and on which days or seeds evaluation runs.

??? note "In the original code"

    | Point | In the code |
    |---|---|
    | Networks | DTDE: RLlib's defaults (PPO, APPO: 2 × 256 tanh, shared encoder). CTCE, CTDE: custom, 2 × 128 ReLU, shared encoder; CTDE adds per-agent 3-layer acting heads (§2) |
    | Budget | `iters` training iterations; PPO samples 4000 environment steps per iteration (≈ 166 days of 24 steps) |
    | PPO | 30 epochs, minibatches of 128, $\lambda$ = 0.95, `kl_coeff` 0 |
    | APPO | RLlib's defaults: batches of 500, buffer of 4 batches, clip 0.4, $\lambda$ 0.95 set |
    | SAC | RLlib's defaults: batch 256, warm-up 1500 steps, `tau` 0.005; uniform buffer of 1000, whole episodes |
    | PBT | §5: `lr`, `entropy_coeff`, `lambda_` (SAC: the two learning rates), every `checkpoint_freq` iterations, Ray Tune's 25 % quantile rule |
    | Observation scaling | none: raw values |
    | Discrete action parts | buy if $\alpha > 0.5$; partner `int(β)` (§1.1) |
    | Evaluation | in parallel with training, every iteration, "auto" duration, on the training environment and seed |
