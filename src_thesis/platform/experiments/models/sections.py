"""The sections of the experiment file as typed models (02 §3).

Why: the file is the interface between the Studio, the CLI, the services and the
runs. As plain dictionaries any key was accepted and a misspelt one silently fell
back to its default; as models every section states its fields and types, an
unknown key is an error, and readers use attributes instead of string keys.

Every field is optional and ``None`` by default: a field that is not set stays
unset (it is not written back) and takes its default only when a run is resolved
(``resolve.DEFAULTS``). Numbers keep the type they are written with (``600``
stays an integer), so a file reads and writes back unchanged.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict

# An integer stays an integer, a float a float (smart union): files round-trip.
Number = Union[int, float]


class Section(BaseModel):
    """A part of the experiment file: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- time
class DayFilter(Section):
    """Which days a sampler may draw (02 §3.2)."""

    season: Literal["winter", "spring", "summer", "autumn"] | None = None
    months: list[int] | None = None
    day_type: Literal["workday", "weekend"] | None = None


class Days(Section):
    """The days episodes cover; evaluation days are held out (02 §3.2)."""

    mode: Literal["fixed", "range", "sampler"] | None = None
    date: str | None = None
    start: str | None = None
    end: str | None = None
    filter: DayFilter | None = None
    eval_holdout: Number | list[str] | None = None
    seed: int | None = None


class TimeSection(Section):
    """``time``: step length, episode length and days (02 §3.2)."""

    resolution: Literal["hourly_aggregated", "native_15min"] | None = None
    horizon_steps: int | None = None
    days: Days | None = None


# --------------------------------------------------------------------------- grid
class GridSource(Section):
    """Which network (``grid.source``)."""

    type: Literal["simbench", "pandapower_builtin", "pandapower_file"] | None = None
    code: str | None = None
    name: str | None = None
    path: str | None = None
    sha256: str | None = None


class Background(Section):
    """What the elements no agent owns do (01 §3.5)."""

    mode: Literal["mapped_replacement", "scaled_background", "no_background"] | None = (
        None
    )
    scale: Number | None = None
    profiles: Literal["native", "static", "catalog"] | None = None


class Limits(Section):
    """Voltage band and loading limits; ``None`` voltages use the network's (D-15)."""

    v_min_pu: Number | None = None
    v_max_pu: Number | None = None
    line_max_percent: Number | None = None
    trafo_max_percent: Number | None = None


class RatingRule(Section):
    """Ratings derived from the base case."""

    type: Literal["base_case_margin"] | None = None
    factor: Number | None = None


class Ratings(Section):
    """Where line and transformer ratings come from."""

    source: Literal["network", "file", "rule", "none"] | None = None
    rule: RatingRule | None = None
    path: str | None = None


class PowerFlow(Section):
    """pandapower ``runpp`` settings."""

    algorithm: Literal["nr", "iwamoto_nr", "bfsw", "gs", "fdbx", "fdxb"] | None = None
    tolerance_mva: Number | None = None
    max_iteration: int | None = None
    init: Literal["results", "auto", "flat", "dc"] | None = None


class Reactive(Section):
    """Reactive power of loads."""

    load: Literal["profile_ratio", "fixed_pf"] | None = None
    fallback_pf: Number | None = None


class Assessment(Section):
    """Whether grid results feed back into learning, and power-flow failures."""

    mode: Literal["shadow", "feedback"] | None = None
    non_convergence: Literal["fail_run", "truncate_episode"] | None = None
    non_convergence_penalty: Number | None = None


class GridSection(Section):
    """``grid`` (02 §3.3)."""

    source: GridSource | None = None
    background: Background | None = None
    limits: Limits | None = None
    ratings: Ratings | None = None
    power_flow: PowerFlow | None = None
    reactive: Reactive | None = None
    assessment: Assessment | None = None


# --------------------------------------------------------------------------- participants
class Owns(Section):
    """Network elements an agent replaces (01 §3.2)."""

    loads: list[str] | None = None
    sgens: list[str] | None = None
    storage: list[str] | None = None


class ProfileRef(Section):
    """A demand or generation profile: a catalogue type or a CSV column."""

    type: str | None = None
    path: str | None = None
    column: str | None = None
    sha256: str | None = None


class ParticipantProfile(Section):
    """Where an agent's demand and generation come from (01 §3.3)."""

    source: Literal["native", "catalog", "csv", "synthetic"] | None = None
    demand: ProfileRef | None = None
    generation: ProfileRef | None = None


class Scaling(Section):
    """How an agent's profiles are scaled (01 §3.4)."""

    mode: Literal["none", "peak_kw", "energy_kwh"] | None = None
    demand: Number | None = None
    generation: Number | None = None


class BatterySpec(Section):
    """An agent's battery (02 §3.4)."""

    nominal_capacity_kwh: Number | None = None
    min_soc: Number | None = None
    max_soc: Number | None = None
    charge_efficiency: Number | None = None
    discharge_efficiency: Number | None = None
    max_power_kw: Number | None = None
    initial_soc: Number | Literal["random"] | None = None


class Participant(Section):
    """One agent: where it sits, what it owns, what drives it (02 §3.4)."""

    id: str
    role: str | None = None
    bus: str | None = None
    owns: Owns | None = None
    profile: ParticipantProfile | None = None
    scaling: Scaling | None = None
    battery: BatterySpec | None = None


# --------------------------------------------------------------------------- market, dso
class Bounds(Section):
    """A minimum and a maximum."""

    min: Number | None = None
    max: Number | None = None


class Ledger(Section):
    """The hash-chained trade log."""

    enabled: bool | None = None
    difficulty: int | None = None


class MarketSection(Section):
    """``market`` (02 §3.5)."""

    mechanism: (
        Literal[
            "average",
            "buyer",
            "seller",
            "bid_ask_spread",
            "nash_bargaining",
            "proportional_surplus",
        ]
        | None
    ) = None
    price: Bounds | None = None
    quantity: Bounds | None = None
    partner_preference: bool | None = None
    match_threshold: Number | None = None
    ledger: Ledger | None = None
    async_orders: bool | None = None


class Tariffs(Section):
    """Feed-in tariff and utility price (02 §3.6)."""

    source: Literal["csv", "synthetic"] | None = None
    feed_in: ProfileRef | None = None
    utility: ProfileRef | None = None
    mode: Literal["normalized", "absolute"] | None = None
    reset_per_episode: bool | None = None


class Fees(Section):
    """Grid fees (eq. 8)."""

    charged: bool | None = None
    congestion_factor: Number | None = None
    congestion_threshold: Number | None = None
    distance_factor: Number | None = None
    voltage_factor: Number | None = None
    voltage_threshold: Number | None = None
    instability_threshold: Number | None = None
    imbalance_factor: Number | None = None
    zone_factor: Number | None = None


class DsoSection(Section):
    """``dso`` (02 §3.6)."""

    tariffs: Tariffs | None = None
    fees: Fees | None = None


# --------------------------------------------------------------------------- environment
class Observation(Section):
    """What agents observe."""

    version: str | None = None
    forecast_error: Number | None = None
    forecast_anchors: int | None = None
    include_partner_reputation: bool | None = None
    own_bus_voltage: Literal["private", "public", "off"] | None = None


class GridViolation(Section):
    """How grid violations enter the reward (D-11)."""

    attribution: Literal["shared", "bus", "marginal"] | None = None
    w_voltage: Number | None = None
    w_loading: Number | None = None
    w_nonconvergence: Number | None = None


class Reward(Section):
    """The reward and its weights (eq. 3–6)."""

    version: str | None = None
    log_scale: Number | None = None
    base_weights: dict[str, Number] | None = None
    cooperation_weights: dict[str, Number] | None = None
    penalties: dict[str, Number] | None = None
    contribution_weights: dict[str, Number] | None = None
    grid_violation: GridViolation | None = None


class Reputation(Section):
    """Reputation weights (eq. 12) and decay."""

    weights: dict[str, Number] | None = None
    decay: Literal["time_of_day", "constant"] | None = None
    decay_factor: Number | None = None


class EnvironmentSection(Section):
    """``environment`` (02 §3.7)."""

    observation: Observation | None = None
    reward: Reward | None = None
    reputation: Reputation | None = None


# --------------------------------------------------------------------------- learning
class Budget(Section):
    """How long each run trains."""

    unit: Literal["env_steps", "iterations", "episodes"] | None = None
    value: int | None = None


class ParadigmOption(Section):
    """Options of one paradigm."""

    reward_aggregation: Literal["sum", "mean"] | None = None
    critic_input: Literal["joint_obs_actions", "joint_obs"] | None = None
    policy_sharing: Literal["independent", "shared"] | None = None


class ParadigmOptions(Section):
    """Per paradigm."""

    ctce: ParadigmOption | None = None
    ctde: ParadigmOption | None = None
    dtde: ParadigmOption | None = None


class ModelSpec(Section):
    """Network model of the policies."""

    embeddings_dim: int | None = None
    dtde_hiddens: list[int] | None = None
    activation: str | None = None


class Tuning(Section):
    """Hyperparameter tuning (PBT)."""

    method: Literal["none", "pbt"] | None = None
    num_samples: int | None = None
    perturbation_interval: int | None = None
    metric: str | None = None
    mutations: dict[str, dict[str, Any]] | None = None


class Rollout(Section):
    """Rollout workers."""

    num_env_runners: int | None = None
    envs_per_runner: int | None = None
    rollout_fragment_length: int | None = None


class Checkpoint(Section):
    """Checkpoints."""

    every: int | None = None
    keep: int | None = None
    score: str | None = None


Paradigm = Literal["ctce", "ctde", "dtde"]
Algorithm = Literal["ppo", "appo", "sac"]


class LearningSection(Section):
    """``learning`` (02 §3.8). Hyperparameters per algorithm stay open: they are
    RLlib's (the pinned version's names).
    """

    paradigms: list[Paradigm] | None = None
    algorithms: list[Algorithm] | None = None
    seeds: list[int] | None = None
    budget: Budget | None = None
    paradigm_options: ParadigmOptions | None = None
    model: ModelSpec | None = None
    algorithm_params: dict[Algorithm, dict[str, Any]] | None = None
    tuning: Tuning | None = None
    rollout: Rollout | None = None
    checkpoint: Checkpoint | None = None


class EvaluationSection(Section):
    """``evaluation`` (02 §3.9)."""

    interval: int | None = None
    episodes: int | Literal["auto"] | None = None
    days: Literal["holdout", "train"] | list[str] | None = None
    explore: bool | None = None
    seeds: list[int] | None = None
    parallel_to_training: bool | None = None
    metrics: list[str] | None = None


class RuleBaseline(Section):
    """A rule-based baseline with parameters (02 §3.10)."""

    name: Literal["rule_based"]
    strategy: Literal["net_position"] | None = None


Baseline = Union[Literal["no_order", "random", "rule_based"], RuleBaseline]


class SweepSection(Section):
    """``sweep`` (02 §3.11): dotted path -> values."""

    mode: Literal["grid", "zip"] | None = None
    parameters: dict[str, list[Any]] | None = None
    labels: list[str] | None = None


class ResourcesSection(Section):
    """``resources`` (02 §3.12)."""

    cpus_per_run: int | None = None
    gpus_per_learner: int | None = None
    max_parallel_runs: int | None = None
    store: str | None = None


class OutputsSection(Section):
    """``outputs`` (02 §3.13)."""

    record_steps: Literal["none", "evaluation", "all"] | None = None
    grid_element_results: bool | None = None
    figures: list[str] | None = None
