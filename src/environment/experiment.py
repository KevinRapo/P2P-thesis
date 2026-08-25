"""Small immutable declarations for reproducible scenario splits."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Tuple

import numpy as np


@dataclass(frozen=True)
class ScenarioSplit:
    """Disjoint scenario IDs and seed lists for train/validation/test use."""

    train_ids: Tuple[str, ...]
    validation_ids: Tuple[str, ...]
    test_ids: Tuple[str, ...]
    training_seeds: Tuple[int, ...]
    evaluation_seeds: Tuple[int, ...]
    test_seeds: Tuple[int, ...]

    def __post_init__(self) -> None:
        groups = (self.train_ids, self.validation_ids, self.test_ids)
        if any(not group for group in groups):
            raise ValueError("Train, validation, and test scenario ID sets must be non-empty.")
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("Scenario ID lists must not contain duplicates.")
        if len(set().union(*map(set, groups))) != sum(len(set(group)) for group in groups):
            raise ValueError("Train, validation, and test scenario IDs must be disjoint.")
        seed_groups = (self.training_seeds, self.evaluation_seeds, self.test_seeds)
        if any(not group for group in seed_groups):
            raise ValueError("Training, evaluation, and test seed lists must be non-empty.")
        if any(len(set(group)) != len(group) for group in seed_groups):
            raise ValueError("Seed lists must not contain duplicates.")
        if len(set().union(*map(set, seed_groups))) != sum(len(set(group)) for group in seed_groups):
            raise ValueError("Training, evaluation, and test seed lists must be disjoint.")

    def as_dict(self) -> Dict[str, list]:
        return {"train_ids": list(self.train_ids),
                "validation_ids": list(self.validation_ids),
                "test_ids": list(self.test_ids),
                "training_seeds": list(self.training_seeds),
                "evaluation_seeds": list(self.evaluation_seeds),
                "test_seeds": list(self.test_seeds)}

    def fingerprint(self) -> str:
        """Return a stable identity for the declared split contents."""
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def require_phase_scenario(self, phase: str, scenario_id: str) -> Tuple[int, ...]:
        """Return the declared seeds only when a scenario belongs to ``phase``."""
        phase_sets = {"train": (self.train_ids, self.training_seeds),
                      "validation": (self.validation_ids, self.evaluation_seeds),
                      "test": (self.test_ids, self.test_seeds)}
        if phase not in phase_sets:
            raise ValueError("phase must be 'train', 'validation', or 'test'.")
        scenario_ids, seeds = phase_sets[phase]
        if scenario_id not in scenario_ids:
            raise ValueError(f"Scenario {scenario_id!r} is not declared for the {phase} split.")
        return seeds


class EpisodeRecordStore:
    """Append immutable episode records and summarize numeric distributions."""

    filename = "episode_records.jsonl"

    def __init__(self, run_directory: Path) -> None:
        self.path = Path(run_directory) / self.filename

    def create(self) -> Path:
        """Create an empty record stream without overwriting an existing run."""
        self.path.touch(exist_ok=False)
        return self.path

    def append(self, record: Dict) -> None:
        """Append one JSON object; callers own the metric definitions in the manifest."""
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")

    def records(self) -> Iterable[Dict]:
        with self.path.open(encoding="utf-8") as file:
            yield from (json.loads(line) for line in file if line.strip())

    @staticmethod
    def summarize(records: Iterable[Dict], metric: str) -> Dict[str, float]:
        """Return count, mean, sample standard deviation, and normal-approximation CI."""
        values = np.asarray([record[metric] for record in records if metric in record], dtype=float)
        if not len(values):
            return {"count": 0, "mean": 0.0, "std": 0.0, "ci95": 0.0}
        std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        return {"count": int(len(values)), "mean": float(values.mean()), "std": std,
                "ci95": float(1.96 * std / np.sqrt(len(values))) if len(values) > 1 else 0.0}


def run_declared_episodes(environment_factory: Callable[[str], Any],
                          policy: Callable[[Any], Dict],
                          scenario_split: ScenarioSplit,
                          scenario_id: str,
                          phase: str,
                          records: EpisodeRecordStore) -> list[Dict]:
    """Evaluate a policy for every declared seed and append raw episode records.

    ``phase='test'`` is intended to be called only after checkpoint selection;
    the function never substitutes a training or validation scenario.
    """
    seeds = scenario_split.require_phase_scenario(phase, scenario_id)
    completed = []
    for seed in seeds:
        environment = environment_factory(scenario_id)
        environment.reset(seed=seed)
        total_reward = 0.0
        steps = 0
        done = False
        while not done:
            _, rewards, terminated, truncated, _ = environment.step(policy(environment))
            total_reward += float(sum(rewards.values()))
            steps += 1
            done = terminated["__all__"] or truncated["__all__"]
        record = {"phase": phase, "scenario_id": scenario_id, "seed": seed,
                  "steps": steps, "episode_return": total_reward,
                  "mean_agent_reward": total_reward / len(environment.agent_order)}
        records.append(record)
        completed.append(record)
    return completed


def run_declared_training(trainer_factory: Callable[[str, int], Any],
                          scenario_split: ScenarioSplit,
                          scenario_id: str) -> list[Dict[str, Any]]:
    """Run one independent training job for every declared training seed.

    The factory owns scenario construction and storage-path selection. Each
    returned item remains tied to exactly one declared seed, so callers can
    summarize saved raw records without selecting a best single run.
    """
    completed = []
    for seed in scenario_split.require_phase_scenario("train", scenario_id):
        trainer = trainer_factory(scenario_id, seed)
        results, metrics = trainer.train()
        completed.append({"phase": "train", "scenario_id": scenario_id, "seed": seed,
                          "results": results, "metrics": metrics})
    return completed
