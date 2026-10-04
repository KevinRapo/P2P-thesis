"""Step and episode records.

Why: the reward is not the result. To judge a policy you need what actually happened
(orders, trades, settlement, grid state) step by step, both for the Results page's
episode replay and for outcome metrics. Building one record per step and deriving
reward, observation, ``info`` and logs from it means they can never disagree with each
other. Buffering per episode keeps disk writes to one per episode, and the ``mode``
keeps disk use small (by default only evaluation episodes are kept).

The environment builds one step record after settlement and the power flow; it
is the single source for reward, observation, ``info`` and logging. This module
buffers those records per episode and writes them to the store at episode end:

- ``raw/steps.jsonl``: one line per step (only if ``outputs.record_steps`` asks
  for it, by default evaluation episodes only);
- ``metrics/evaluation.jsonl``: one line per evaluation episode with the
  research outcomes, kept apart from RL learning metrics.

The fields of ``StepRecord`` stay dictionaries until the rebuilt environment
(R1, R4) fixes their content; the record shape is what matters here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src_thesis.experiments.store.filesystem import ExperimentStore

RecordMode = Literal["none", "evaluation", "all"]


@dataclass(frozen=True)
class StepRecord:
    """Everything that happened in one step, built once by the environment (05 §3.6).

    Reward, observation, ``info`` and logging are all derived from this record, so
    they cannot disagree.

    Attributes:
        episode: Episode number.
        step: Step within the episode.
        day: Simulated date.
        orders: Orders as submitted.
        trades: Matched trades.
        settlement: Per agent: energy delivered and received, cash.
        assessment: The step's grid assessment, as a dict.
        kpis: Implicit-cooperation KPIs.
        reward_components: Per agent, the value of each reward term.
        rewards: Per agent, the total reward.
    """

    episode: int
    step: int
    day: str
    orders: list[dict[str, Any]] = field(default_factory=list)  # as submitted
    trades: list[dict[str, Any]] = field(default_factory=list)
    settlement: dict[str, Any] = field(default_factory=dict)  # per agent: energy, cash
    assessment: dict[str, Any] = field(default_factory=dict)  # GridAssessment as dict
    kpis: dict[str, float] = field(default_factory=dict)
    reward_components: dict[str, dict[str, float]] = field(default_factory=dict)
    rewards: dict[str, float] = field(default_factory=dict)


class EpisodeRecorder:
    """Buffers one episode's steps and writes them when the episode ends."""

    def __init__(self, store: ExperimentStore, run_id: str, mode: RecordMode) -> None:
        self.store = store
        self.run_id = run_id
        self.mode = mode
        self._steps: list[StepRecord] = []
        self._episode: int | None = None
        self._day = ""
        self._evaluation = False

    def start_episode(self, episode: int, day: str, evaluation: bool) -> None:
        """Begin buffering a new episode.

        Args:
            episode: Episode number.
            day: Simulated date.
            evaluation: True for evaluation episodes (the only ones kept in the default
                ``"evaluation"`` mode).
        """
        self._steps = []
        self._episode, self._day, self._evaluation = episode, day, evaluation

    def record(self, step: StepRecord) -> None:
        """Buffer one step, if this episode is kept (see ``mode``)."""
        if self._episode is None:
            raise RuntimeError("record() before start_episode()")
        if self._keeps_steps():
            self._steps.append(step)

    def end_episode(self, outcomes: dict[str, float]) -> None:
        """Flush the buffered steps and, for evaluation episodes, the outcomes."""
        if self._episode is None:
            raise RuntimeError("end_episode() before start_episode()")
        for step in self._steps:
            self.store.append_jsonl(self.run_id, "raw/steps.jsonl", asdict(step))
        if self._evaluation:
            self.store.append_jsonl(
                self.run_id,
                "metrics/evaluation.jsonl",
                {"episode": self._episode, "day": self._day, **outcomes},
            )
        self._steps, self._episode = [], None

    def _keeps_steps(self) -> bool:
        return self.mode == "all" or (self.mode == "evaluation" and self._evaluation)
