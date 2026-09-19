"""
Multi-agent reinforcement learning training implementation using Ray RLlib.
"""

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from datetime import datetime
from os import cpu_count
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple
from uuid import uuid4

from gymnasium import Env

# Windows PyTorch wheels commonly omit libuv, while Ray's TCP rendezvous defaults
# to it. Set this before worker processes are spawned; explicit user settings win.
if os.name == "nt":
    os.environ.setdefault("USE_LIBUV", "0")
# We explicitly install portable CSV/JSON callbacks below. Prevent Ray from
# adding TensorBoardX as a duplicate default logger on Windows paths.
os.environ.setdefault("TUNE_DISABLE_AUTO_CALLBACK_LOGGERS", "1")

import ray
from gymnasium import spaces
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.algorithms.algorithm_config import AlgorithmConfig
from ray.rllib.algorithms.appo import APPOConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.algorithms.sac.torch.sac_torch_learner import SACTorchLearner
from ray.rllib.callbacks.callbacks import RLlibCallback
from ray.rllib.core.learner.learner import Learner
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.policy.policy import PolicySpec
from ray.rllib.utils.metrics import (
    ENV_RUNNER_RESULTS,
    EPISODE_RETURN_MEAN,
    EVALUATION_RESULTS,
)
from ray.rllib.utils.typing import MultiAgentDict
from ray.tune import (
    CheckpointConfig,
    ResultGrid,
    RunConfig,
    TuneConfig,
    Tuner,
    loguniform,
)
from ray.tune.logger import CSVLoggerCallback, JsonLoggerCallback
from ray.tune.result import DONE, TRAINING_ITERATION
from ray.tune.schedulers import PopulationBasedTraining
from torch import Tensor
from torch.cuda import device_count, is_available

from .base import RLAlgorithm, TrainingMode
from .ctce import CTCEModule
from .ctde import CTDEModule
from .io import EnvConfigHandler
from .lem import LocalEnergyMarket


def extract_run_metrics(
    metrics: Dict[str, Any],
    num_agents: int = 1,
    decentralized: bool = False,
    target_env_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Extract comparable reward/budget metrics across RLlib API versions.

    RLlib exposes lifetime counters both at the result root and under
    ``env_runners`` depending on version/API stack.  This helper deliberately
    prefers the root value and falls back to the nested value.  DTDE episode
    returns are sums across agents, so the comparison fields are always
    converted to per-agent means.
    """
    metrics = metrics or {}
    runners = metrics.get("env_runners") or {}
    evaluation = metrics.get("evaluation") or {}
    eval_runners = evaluation.get("env_runners") or {}

    def value(
        key: str, source: Dict[str, Any] = metrics, nested: Dict[str, Any] = runners
    ):
        return source.get(key, nested.get(key))

    scale = max(1, int(num_agents)) if decentralized else 1
    raw_reward = value("episode_return_mean")
    # RLlib has emitted evaluation returns both under ``evaluation`` /
    # ``env_runners`` and directly under ``evaluation`` across releases.
    raw_eval_reward = eval_runners.get(
        "episode_return_mean", evaluation.get("episode_return_mean")
    )
    steps = value("num_env_steps_sampled_lifetime")
    episodes = value("num_episodes_lifetime")
    # These are different units.  ``num_training_step_calls_per_iteration``
    # is an optimizer/update-call count; ``num_env_steps_trained_lifetime``
    # is the number of samples consumed by the learner.  Never use the latter
    # as a fallback for the former.
    learner_updates = value("num_training_step_calls_per_iteration")
    learners = metrics.get("learners") or {}
    learner_train_steps = learners.get("num_env_steps_trained_lifetime")
    if learner_train_steps is None:
        all_modules = learners.get("__all_modules__") or {}
        learner_train_steps = all_modules.get("num_env_steps_trained_lifetime")
    report = {
        "raw_reward": float(raw_reward) if raw_reward is not None else None,
        "raw_eval_reward": float(raw_eval_reward)
        if raw_eval_reward is not None
        else None,
        "comparison_reward": (
            float(raw_reward) / scale if raw_reward is not None else None
        ),
        "comparison_eval_reward": (
            float(raw_eval_reward) / scale if raw_eval_reward is not None else None
        ),
        "sampled_env_steps": int(steps) if steps is not None else None,
        "sampled_episodes": int(episodes) if episodes is not None else None,
        "learner_updates": int(learner_updates)
        if learner_updates is not None
        else None,
        "learner_train_steps": int(learner_train_steps)
        if learner_train_steps is not None
        else None,
    }
    if target_env_steps is not None and report["sampled_env_steps"] is not None:
        report["requested_env_steps"] = int(target_env_steps)
        report["env_step_overshoot"] = max(
            0, report["sampled_env_steps"] - int(target_env_steps)
        )
        report["budget_reached"] = report["sampled_env_steps"] >= int(target_env_steps)
    return report


# region Training orchestration
class RLTrainer:
    """Manages training using Ray RLlib with support for multiple algorithms."""

    # region Initialization and validation
    def __init__(
        self,
        env_config: Dict[str, Any],
        algorithm: RLAlgorithm = RLAlgorithm.PPO,
        training: TrainingMode = TrainingMode.DTDE,
        iters: int = 100,
        tune_samples: int = 1,
        checkpoint_freq: int = 10,
        evaluation_interval: Optional[int] = None,
        evaluation_duration: int | Literal["auto"] = "auto",
        evaluation_env_config: Optional[Dict[str, Any]] = None,
        env_steps: Optional[int] = None,
        cpus: Optional[int] = None,
        gpus: Optional[int] = None,
        train_batch_size: Optional[int] = None,
        storage_path: Optional[str] = None,
        num_env_runners: Optional[int] = None,
        ray_cpus: Optional[int] = None,
        max_concurrent_trials: Optional[int] = None,
    ):
        """Initialize the RL trainer.

        Args:
            env_config: Environment configuration dictionary
            algorithm: RL algorithm to use (PPO, APPO, SAC)
            training: Training mode (CTCE, CTDE, DTDE)
            iters: Number of training iterations
            tune_samples: Number of samples for tuning
            checkpoint_freq: Frequency of checkpoints
            evaluation_interval: Frequency of held-out evaluation; disabled by default
            evaluation_duration: Duration of evaluation
            evaluation_env_config: Separately seeded evaluation scenario configuration
            cpus: Legacy alias for the number of parallel environment runners.
            gpus: Number of GPUs per learner
            train_batch_size: Optional PPO batch size; useful for short smoke runs
            storage_path: Path to store training results
            env_steps: Optional common sampled-environment-step stopping budget
            num_env_runners: Environment runner actors allocated to each trial.
            ray_cpus: Total CPU resource units exposed to the Ray cluster.
            max_concurrent_trials: Maximum Tune trials allowed to run at once.
        """
        self.env_config = deepcopy(env_config)
        self.algorithm = algorithm
        self.training = training
        self.iters = iters
        self.tune_samples = tune_samples
        self.checkpoint_freq = checkpoint_freq
        self.evaluation_interval = evaluation_interval
        self.evaluation_duration = evaluation_duration
        self.evaluation_env_config = (
            deepcopy(evaluation_env_config)
            if evaluation_env_config is not None
            else deepcopy(self.env_config)
        )
        if evaluation_env_config is None:
            train_seed = self.env_config.get("seed")
            self.evaluation_env_config["seed"] = (
                (int(train_seed) + 10000) if train_seed is not None else 10000
            )
        self.evaluation_env_config.setdefault("evaluation_split", "held_out")
        self.env_steps = env_steps
        # Keep the historical ``cpus`` argument as a backwards-compatible
        # alias, while allowing cluster capacity and per-trial sampling
        # parallelism to be configured independently.
        requested_cpus = self._get_cpus_count() if cpus is None else cpus
        self.num_env_runners = (
            requested_cpus if num_env_runners is None else num_env_runners
        )
        self.ray_cpus = (
            requested_cpus + 2 if ray_cpus is None else ray_cpus
        )
        self.max_concurrent_trials = max_concurrent_trials
        # ``self.cpus`` remains an internal compatibility alias for callers
        # that inspect the old attribute.
        self.cpus = self.num_env_runners
        self.gpus = self._get_cuda_gpu_count() if gpus is None else gpus
        self.train_batch_size = train_batch_size
        # Ray/pyarrow require an absolute filesystem URI for Tune storage.
        self.storage_path = (
            str(Path(storage_path).resolve()) if storage_path is not None else None
        )

        # Validate initialization parameters
        self._check_init()

        # Initialize environment
        self.env: MultiAgentEnv = (
            LocalEnergyMarket(env_config)
            if self.training == TrainingMode.DTDE
            else GroupedLEM(env_config)
        )

    def _check_init(self) -> None:
        """Validate initialization parameters to ensure proper configuration."""
        # Validate algorithm
        if not isinstance(self.algorithm, RLAlgorithm):
            raise ValueError(
                f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC']."
            )

        # Validate training mode
        if not isinstance(self.training, TrainingMode):
            raise ValueError(
                f"The <training> must be a TrainingMode enum, got <training = {self.training}>, supported training modes: ['CTCE', 'CTDE', 'DTDE']."
            )

        # Validate positive integers
        if not isinstance(self.cpus, int) or self.cpus <= 0:
            raise ValueError(
                f"The <cpus> must be a positive integer, got <cpus = {self.cpus}>."
            )

        if not isinstance(self.num_env_runners, int) or self.num_env_runners <= 0:
            raise ValueError(
                "The <num_env_runners> must be a positive integer."
            )

        if not isinstance(self.ray_cpus, int) or self.ray_cpus <= 0:
            raise ValueError("The <ray_cpus> must be a positive integer.")

        if self.ray_cpus < self.num_env_runners + 1:
            raise ValueError(
                "<ray_cpus> must cover the configured environment runners "
                "and the trial main process."
            )

        if self.max_concurrent_trials is not None and (
            not isinstance(self.max_concurrent_trials, int)
            or self.max_concurrent_trials <= 0
        ):
            raise ValueError(
                "The <max_concurrent_trials> must be a positive integer or None."
            )

        if not isinstance(self.gpus, int) or self.gpus < 0:
            raise ValueError(
                f"The <gpus> must be a non-negative integer, got <gpus = {self.gpus}>."
            )

        train_batch_size = getattr(self, "train_batch_size", None)
        if train_batch_size is not None and (
            not isinstance(train_batch_size, int)
            or isinstance(train_batch_size, bool)
            or train_batch_size <= 0
        ):
            raise ValueError(
                "The <train_batch_size> must be a positive integer or None."
            )

        if not isinstance(self.iters, int) or self.iters <= 0:
            raise ValueError(
                f"The <iters> must be a positive integer, got <iters = {self.iters}>."
            )

        if self.env_steps is not None and (
            not isinstance(self.env_steps, int) or self.env_steps <= 0
        ):
            raise ValueError(
                f"The <env_steps> must be a positive integer or None, got <env_steps = {self.env_steps}>."
            )

        if not isinstance(self.tune_samples, int) or self.tune_samples <= 0:
            raise ValueError(
                f"The <tune_samples> must be a positive integer, got <tune_samples = {self.tune_samples}>."
            )

        if not isinstance(self.checkpoint_freq, int) or self.checkpoint_freq <= 0:
            raise ValueError(
                f"The <checkpoint_freq> must be a positive integer, got <checkpoint_freq = {self.checkpoint_freq}>."
            )

        if self.evaluation_interval is not None:
            if (
                not isinstance(self.evaluation_interval, int)
                or self.evaluation_interval <= 0
            ):
                raise ValueError(
                    f"The <evaluation_interval> must be a positive integer or None, got <evaluation_interval = {self.evaluation_interval}>."
                )

        if not (
            (
                isinstance(self.evaluation_duration, str)
                and self.evaluation_duration == "auto"
            )
            or (
                isinstance(self.evaluation_duration, int)
                and not isinstance(self.evaluation_duration, bool)
                and self.evaluation_duration > 0
            )
        ):
            raise ValueError(
                f"The <evaluation_duration> must be a positive integer or 'auto', got <evaluation_duration = {self.evaluation_duration}>."
            )

        # Short runs still save their final checkpoint when the periodic
        # checkpoint interval is longer than the requested training budget.

        # Validate storage path if provided
        if self.storage_path is not None:
            storage_path = Path(self.storage_path)
            if not storage_path.parent.exists():
                raise ValueError(
                    f"The storage path parent directory does not exist: <storage_path = {storage_path.parent}>."
                )

        # Validate environment configuration
        if not isinstance(self.env_config, dict):
            raise ValueError(
                f"The <env_config> must be a dictionary, got <env_config = {self.env_config}>."
            )

        # Check required environment configuration keys
        for key in ["max_steps", "market_config", "agents"]:
            if key not in self.env_config:
                raise ValueError(
                    f"The <env_config> is missing the required key: <key = {key}>."
                )

        # Validate max_steps
        if (
            not isinstance(self.env_config["max_steps"], int)
            or self.env_config["max_steps"] <= 0
        ):
            raise ValueError(
                f"The <max_steps> must be a positive integer, got <max_steps = {self.env_config['max_steps']}>."
            )

        if (
            train_batch_size is not None
            and train_batch_size < self.env_config["max_steps"]
        ):
            raise ValueError(
                "The <train_batch_size> must cover at least one complete environment episode "
                "so Tune receives the declared episode-return selection metric."
            )

        # Validate agents
        if (
            not isinstance(self.env_config["agents"], list)
            or len(self.env_config["agents"]) == 0
        ):
            raise ValueError(
                f"The <agents> must be a non-empty list, got <agents = {self.env_config['agents']}>."
            )

    # endregion

    # region Runtime and algorithm configuration
    @staticmethod
    def _get_cpus_count() -> int:
        """
        Get the number of CPUs available.

        Returns:
            int: The number of CPUs available.
        """
        return max(1, cpu_count() - 4)

    @staticmethod
    def _get_cuda_gpu_count() -> int:
        """
        Get the number of CUDA GPUs available.

        Returns:
            int: The number of CUDA GPUs available.
        """
        return device_count() if is_available() else 0

    def _setup_config(
        self, embeddings_dim: int = 128
    ) -> Tuple[AlgorithmConfig, Dict[str, Any]]:
        """
        Setup the algorithm configuration based on the specified algorithm type,
        and dynamically select valid hyperparameters for PBT based on algorithm.

        Args:
            embeddings_dim: The dimension of the embeddings.

        Returns:
            Tuple[AlgorithmConfig, Dict[str, Any]]: Tuple containing the algorithm configuration
            and the hyperparameter mutations.
        """
        # Define only algorithm-valid PBT mutations.
        if self.algorithm == RLAlgorithm.PPO:
            hyperparam_mutations = {
                "lr": loguniform(0.000001, 0.001),
                "entropy_coeff": loguniform(0.0001, 0.1),
                "lambda_": loguniform(0.8, 0.99),
                # "clip_param": loguniform(0.1, 0.3),
            }

        elif self.algorithm == RLAlgorithm.APPO:
            hyperparam_mutations = {
                "lr": loguniform(0.000001, 0.001),
                "entropy_coeff": loguniform(0.0001, 0.1),
                "lambda_": loguniform(0.8, 0.99),
            }

        elif self.algorithm == RLAlgorithm.SAC:
            hyperparam_mutations = {
                "actor_lr": loguniform(0.000001, 0.001),
                "critic_lr": loguniform(0.000001, 0.001),
                # "tau": loguniform(0.001, 0.01),  # Soft update, if configurable
            }

        else:
            raise ValueError(
                f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC']."
            )

        # Compose algorithm, resource, evaluation, and mode settings.
        config = self._setup_algorithm_config()
        if self.train_batch_size is not None:
            if self.algorithm == RLAlgorithm.SAC:
                config = config.training(
                    train_batch_size_per_learner=self.train_batch_size,
                    num_steps_sampled_before_learning_starts=self.train_batch_size,
                )
                config = config.reporting(
                    min_sample_timesteps_per_iteration=self.train_batch_size,
                    min_time_s_per_iteration=0,
                )
            elif self.algorithm == RLAlgorithm.APPO:
                config = config.training(
                    train_batch_size_per_learner=self.train_batch_size
                )
                config = config.reporting(min_time_s_per_iteration=0)
        config = self._setup_extra_config(config)
        config = self._setup_training_config(config, embeddings_dim)

        config = config.debugging(seed=self.env_config.get("seed"))
        return config, hyperparam_mutations

    def _setup_algorithm_config(self) -> AlgorithmConfig:
        """
        Setup the algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration.
        """
        if self.algorithm == RLAlgorithm.PPO:
            train_batch_size = getattr(self, "train_batch_size", None)
            training_options = {
                "lr": 1e-5,
                "gamma": 0.99,
                "use_critic": True,
                "use_gae": True,
                "lambda_": 0.95,
                "num_epochs": 30,
                "minibatch_size": min(128, train_batch_size)
                if train_batch_size
                else 128,
                "kl_coeff": 0.0,
                "entropy_coeff": 0.01,
                "clip_param": 0.2,
                "grad_clip": 0.5,
            }
            if train_batch_size is not None:
                training_options["train_batch_size"] = train_batch_size
            return PPOConfig().training(**training_options)

        elif self.algorithm == RLAlgorithm.APPO:
            return APPOConfig().training(
                lr=1e-5,
                vtrace=True,
                lambda_=0.95,
                kl_coeff=0.0,
                entropy_coeff=0.01,
                grad_clip=0.5,
            )

        elif self.algorithm == RLAlgorithm.SAC:
            if self.training in [TrainingMode.CTCE, TrainingMode.CTDE]:
                # Centralized policies emit one joint action.
                target_entropy = -sum(
                    space.shape[0] for space in self.env.action_space["grouped_agents"]
                )
                replay_buffer_type = "EpisodeReplayBuffer"
            else:
                # Decentralized policies each emit one local action.
                target_entropy = -self.env.action_spaces[self.env.agents_id[0]].shape[0]
                replay_buffer_type = "MultiAgentEpisodeReplayBuffer"

            return (
                SACConfig()
                .training(
                    actor_lr=1e-5,
                    critic_lr=1e-5,
                    gamma=0.99,
                    twin_q=True,
                    target_entropy=target_entropy,
                    grad_clip=0.5,
                    replay_buffer_config={
                        "type": replay_buffer_type,
                        "capacity": int(1e3),
                        "replay_sequence_length": 1,
                        "replay_burn_in": 0,
                        "replay_zero_init_states": True,
                    },
                )
                .env_runners(batch_mode="complete_episodes")
            )

        else:
            raise ValueError(
                f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC']."
            )

    def _setup_extra_config(self, config: AlgorithmConfig) -> AlgorithmConfig:
        """
        Setup the extra configuration.

        Args:
            config: The algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration with the extra configuration.
        """
        # Windows uses one local learner because standard wheels omit NCCL.
        num_learners = 0 if os.name == "nt" else 1
        if self.algorithm == RLAlgorithm.SAC and self.training != TrainingMode.DTDE:
            # Ray 2.x exposes this custom learner through ``training``; newer
            # releases warn about the spelling but this remains the compatible
            # API for the pinned environment used by the baseline.
            config = config.training(learner_class=GroupedSACTorchLearner)
        # The comparison budget is expressed in complete market transitions.
        # Keeping episode fragments out of learner batches makes the reported
        # episode-return metric available for every algorithm and avoids a
        # PPO/APPO run ending on an incomplete 24-hour episode.  The resulting
        # final batch may overshoot ``env_steps``; that amount is reported by
        # ``extract_run_metrics`` rather than silently treated as equivalent.
        configured = (
            config.framework("torch")
            .env_runners(
                num_env_runners=self.num_env_runners,
                sample_timeout_s=None,
                batch_mode="complete_episodes",
            )
            .learners(num_learners=num_learners, num_gpus_per_learner=self.gpus)
        )
        if self.algorithm == RLAlgorithm.APPO:
            # Require each asynchronous iteration to contain real work.
            configured = configured.reporting(
                min_sample_timesteps_per_iteration=self.train_batch_size or 512,
                min_train_timesteps_per_iteration=self.train_batch_size or 512,
                min_time_s_per_iteration=1.0,
            )
        if self.evaluation_interval is None:
            # `evaluation_duration="auto"` (the class default) is only valid
            # with `evaluation_parallel_to_training=True`; leaving it
            # unresolved here is harmless for a single build but fails
            # RLlib's stricter re-validation when Tune's PBT scheduler
            # reconstructs this config for a cloned/perturbed trial.
            return configured.evaluation(
                evaluation_interval=None,
                evaluation_duration=1,
                evaluation_parallel_to_training=False,
            )
        return configured.evaluation(
            evaluation_interval=self.evaluation_interval,
            # `evaluation_duration="auto"` is only valid with
            # `evaluation_parallel_to_training=True`; this path always sets
            # it False (evaluation runs on the local worker, not dedicated
            # remote runners), so resolve "auto" to a concrete duration
            # instead of passing it through to RLlib's validator.
            evaluation_duration=(
                1 if self.evaluation_duration == "auto" else self.evaluation_duration
            ),
            evaluation_duration_unit="episodes",
            evaluation_num_env_runners=0,
            evaluation_parallel_to_training=False,
            evaluation_config={
                "explore": False,
                "env_config": deepcopy(self.evaluation_env_config),
            },
        )

    def _get_tune_scheduler(self, hyperparam_mutations: Dict[str, Any]):
        """Use PBT only when there is an actual population to perturb."""
        if self.tune_samples <= 1:
            return None
        return PopulationBasedTraining(
            time_attr=TRAINING_ITERATION,
            perturbation_interval=self.checkpoint_freq,
            hyperparam_mutations=hyperparam_mutations,
            # Multiplicative perturbations escape Domain bounds (the previous
            # runs produced lambda_ > 1).  Always resample from the declared
            # paper-centred ranges so every PBT configuration remains valid.
            resample_probability=1.0,
        )

    def _experiment_name(self) -> str:
        """Return a collision-resistant run identifier without hidden state."""
        # RLlib checkpoints contain deep subdirectories; short components keep
        # PyArrow's Windows file copies below the legacy path-length limit.
        return f"{self.algorithm.value}_{self.training.value}_{uuid4().hex[:8]}"

    @staticmethod
    def write_run_manifest(
        env_config: Dict[str, Any], run_directory: Path, metadata: Dict[str, Any]
    ) -> Path:
        """Write the minimal immutable run description before any training starts."""
        run_directory.mkdir(parents=True, exist_ok=True)
        serialized_environment = EnvConfigHandler._make_config_serializable(
            env_config, decimals=12
        )
        manifest = {
            "schema_version": 3,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata,
            "environment": serialized_environment,
            "unit_contract": {
                "power": "kW",
                "energy": "kWh",
                "time": "hours",
                "price": "currency/kWh",
                "cash": "currency",
            },
            "profile_source_hashes": RLTrainer._profile_source_hashes(
                serialized_environment
            ),
            "repository": RLTrainer._repository_provenance(),
        }
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        path = run_directory / "run_manifest.json"
        with path.open("x", encoding="utf-8") as file:
            json.dump(manifest, file, indent=2)
        return path

    @staticmethod
    def _repository_provenance() -> Dict[str, Any]:
        """Record repository environment and metric-contract identities without mutating the tree."""
        root = Path(__file__).resolve().parents[2]

        def git(*arguments: str) -> Optional[str]:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return completed.stdout.strip() if completed.returncode == 0 else None

        def file_hash(filename: str) -> Optional[str]:
            source = root / filename
            return (
                hashlib.sha256(source.read_bytes()).hexdigest()
                if source.is_file()
                else None
            )

        status = git("status", "--porcelain")
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty_tree": bool(status) if status is not None else None,
            "environment_sha256": file_hash("environment.yml"),
            "metric_contract_sha256": file_hash("docs/metric-contract.md"),
        }

    @staticmethod
    def _start_ray(ray_cpus: int, gpus: int):
        """Start the notebook runtime with the Windows Ray 2.51 port workaround.

        Ray chooses auxiliary ports in the OS ephemeral range, then releases
        them before child services bind. On Windows another Ray service can
        take the same port during startup (WinError 10048). Choose checked
        auxiliary ports below Windows' default 49152+ dynamic range instead.
        The installed Ray package and other running sessions are not changed.
        """
        options = dict(
            # Cluster capacity is intentionally independent from the number
            # of environment runners assigned to one Tune trial.
            num_cpus=ray_cpus,
            num_gpus=gpus,
            include_dashboard=False,
            runtime_env=RLTrainer._ray_runtime_env(),
        )
        # Keep Ray's large temporary object store and logs off synchronized
        # folders such as OneDrive when the caller provides a local path.
        ray_temp_dir = os.environ.get("MARLEM_RAY_TEMP_DIR")
        if ray_temp_dir:
            options["_temp_dir"] = str(Path(ray_temp_dir).resolve())
        if os.name != "nt":
            return ray.init(**options)
        import socket
        from random import SystemRandom
        from unittest.mock import patch

        from ray._private.node import Node

        def unused_port(node, allocated_ports=None):
            allocated_ports = allocated_ports or set()
            for _ in range(100):
                port = SystemRandom().randrange(20000, 40000)
                if port in allocated_ports:
                    continue
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    try:
                        probe.bind(("", port))
                    except OSError:
                        continue
                    return port
            raise RuntimeError("Could not allocate a free local Ray service port.")

        with patch.object(Node, "_get_unused_port", unused_port):
            return ray.init(**options)

    @staticmethod
    def _ray_runtime_env() -> Dict[str, Dict[str, str]]:
        """Expose the repository source root to Ray workers started from notebooks."""
        root = str(Path(__file__).resolve().parents[2])
        existing = os.environ.get("PYTHONPATH", "")
        paths = [
            root,
            *(path for path in existing.split(os.pathsep) if path and path != root),
        ]
        return {"env_vars": {"PYTHONPATH": os.pathsep.join(paths)}}

    @staticmethod
    def _profile_source_hashes(
        serialized_environment: Dict[str, Any],
    ) -> Dict[str, str]:
        """Hash configured replay files so a manifest identifies its data exactly."""
        hashes = {}
        for handler_name in ("der_profile_handler", "dso_profile_handler"):
            handler = serialized_environment.get(handler_name) or {}
            for key, value in handler.items():
                if key.endswith("_file_path") and value:
                    source = Path(value)
                    if not source.is_file():
                        raise FileNotFoundError(
                            f"Configured profile source is missing: {source}"
                        )
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    hashes[str(source)] = digest
        return hashes

    def _setup_training_config(
        self, config: AlgorithmConfig, embeddings_dim: int = 128
    ) -> AlgorithmConfig:
        """
        Setup the training mode configuration.

        Args:
            config: The algorithm configuration.
            embeddings_dim: The dimension of the embeddings.

        Returns:
            AlgorithmConfig: The algorithm configuration with the mode configuration.
        """
        # CTCE: one policy sees the joint observation and action.
        if self.training == TrainingMode.CTCE:
            return (
                config.environment(GroupedLEM, env_config=self.env_config)
                .rl_module(
                    rl_module_spec=RLModuleSpec(
                        module_class=CTCEModule,
                        observation_space=self.env.observation_space,
                        action_space=self.env.action_space,
                        model_config={
                            "algorithm": self.algorithm.value,
                            "embeddings_dim": embeddings_dim,
                        },
                    )
                )
                .callbacks(MultiOptimizerCallback)
            )

        # CTDE: local actors share a centralized training critic.
        elif self.training == TrainingMode.CTDE:
            return (
                config.environment(GroupedLEM, env_config=self.env_config)
                .rl_module(
                    rl_module_spec=RLModuleSpec(
                        module_class=CTDEModule,
                        observation_space=self.env.observation_space,
                        action_space=self.env.action_space,
                        model_config={
                            "algorithm": self.algorithm.value,
                            "agents_id": self.env.original_agents_id,
                            "embeddings_dim": embeddings_dim,
                        },
                    )
                )
                .callbacks(MultiOptimizerCallback)
            )

        # DTDE: each agent owns an independent policy and module.
        elif self.training == TrainingMode.DTDE:
            agents_policy = {
                agent_id: PolicySpec(
                    observation_space=self.env.observation_spaces[agent_id],
                    action_space=self.env.action_spaces[agent_id],
                )
                for agent_id in self.env.agents_id
            }

            # Setup the RL module of each agent
            agents_rl_module = {
                agent_id: RLModuleSpec(
                    module_class=self.algorithm.get_module_class(),
                    observation_space=agents_policy[agent_id].observation_space,
                    action_space=agents_policy[agent_id].action_space,
                    # Honor the same notebook network-size control
                    # used by the centralized training modes.
                    model_config={"fcnet_hiddens": [embeddings_dim, embeddings_dim]},
                )
                for agent_id in self.env.agents_id
            }

            return (
                config.environment(LocalEnergyMarket, env_config=self.env_config)
                .multi_agent(
                    policies=agents_policy,
                    policy_mapping_fn=lambda agent_id, *args, **kwargs: agent_id,
                    count_steps_by="env_steps",
                )
                .rl_module(
                    rl_module_spec=MultiRLModuleSpec(rl_module_specs=agents_rl_module)
                )
                .callbacks(SingleOptimizerCallback)
            )

        else:
            raise ValueError(
                f"The <training> must be a TrainingMode enum, got <training = {self.training}>, supported training modes: ['CTCE', 'CTDE', 'DTDE']."
            )

    def _setup_custom_algo_config(self, config: AlgorithmConfig) -> AlgorithmConfig:
        """
        Setup the custom algorithm config.

        Args:
            config: The algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration with the custom algorithm config.
        """

        class CustomAlgorithm(
            PPOConfig
            if self.algorithm == RLAlgorithm.PPO
            else APPOConfig
            if self.algorithm == RLAlgorithm.APPO
            else SACConfig
        ):
            """
            Custom algorithm config that inherits from the appropriate base class.
            """

            def __init__(self, algo_config):
                """
                Initialize the custom algorithm config.

                Args:
                    algo_config: The algorithm configuration.
                """
                self.algo_config = algo_config

            def reset_config(self, new_config) -> bool:
                """
                Reset the configuration of the algorithm.

                Args:
                    new_config: The new configuration.
                """
                for k, v in new_config.items():
                    setattr(self.algo_config, k, v)
                return True

        return CustomAlgorithm(config)

    # endregion

    # region Training and checkpoint restoration
    def _save_env_config(self, results: ResultGrid) -> None:
        """Save environment configuration to experiment directory.

        Args:
            results: The results of the training and evaluation.
        """
        EnvConfigHandler.save(
            self.env_config,
            storage_path=str(Path(results.get_best_result().path).parent),
            name="env_config",
        )

    def _save_episode_records(self, results: ResultGrid) -> None:
        """Materialize raw episode metrics inside their owning Tune trial.

        RLlib callbacks run inside the Algorithm actor, where Ray 2.51 exposes
        ``trial_id='default'`` even though Tune assigns a real trial ID on the
        driver.  The driver's ResultGrid has the authoritative trial path, so
        writing here is both race-free under PBT and correctly attributable.
        """
        for trial_result in results:
            trial_path = Path(trial_result.path)
            result_path = trial_path / "result.json"
            if not result_path.exists():
                continue
            records = []
            with result_path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    values = row.get(ENV_RUNNER_RESULTS, {})
                    returns = values.get(EpisodeRecordCallback._returns_key, [])
                    lengths = values.get(EpisodeRecordCallback._lengths_key, [])
                    seeds = values.get(EpisodeRecordCallback._seeds_key, [])
                    totals = values.get("group_total_reward", [])
                    means = values.get("group_mean_reward", [])
                    if not isinstance(returns, list) or not isinstance(lengths, list):
                        continue
                    env_config = row.get("config", {}).get("env_config", {})
                    for index, (episode_return, episode_length) in enumerate(
                        zip(returns, lengths)
                    ):
                        record = {
                            "record_type": "training_episode",
                            "phase": "train",
                            "scenario_id": env_config.get("scenario_id"),
                            "seed": (
                                int(seeds[index])
                                if isinstance(seeds, list) and index < len(seeds)
                                else env_config.get("seed")
                            ),
                            "trial_id": trial_path.name,
                            "training_iteration": row.get(TRAINING_ITERATION),
                            "episode_return": float(episode_return),
                            "steps": int(episode_length),
                        }
                        if isinstance(totals, list) and index < len(totals):
                            record["group_total_reward"] = float(totals[index])
                        if isinstance(means, list) and index < len(means):
                            record["group_mean_reward"] = float(means[index])
                        records.append(record)
            record_path = trial_path / "episode_records.jsonl"
            with record_path.open("w", encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record) + "\n")

    def train(
        self,
        embeddings_dim: int = 128,
        _checkpoint_path: Optional[str] = None,
        _iters: Optional[int] = None,
    ) -> Tuple[ResultGrid, Dict[str, Any]]:
        """
        Train the RL algorithm.

        Args:
            embeddings_dim: The dimension of the embeddings.
            _checkpoint_path: The path of the checkpoint to restore an experiment.
            _iters: The number of iterations to train for restored experiments.

        Returns:
            ResultGrid: The results of the training and evaluation.
            Dict[str, Any]: The metrics of the training and evaluation.
        """
        # Build the final immutable training configuration.
        algo_config, hyperparam_mutations = self._setup_config(embeddings_dim)
        # algo_config = self._setup_custom_algo_config(algo_config).algo_config

        if _checkpoint_path:
            algo_config.callbacks(
                on_algorithm_init=lambda algorithm, **kwargs: (
                    algorithm.restore_from_path(_checkpoint_path)
                )
            )

        run_name = self._experiment_name()
        run_storage = (
            Path(self.storage_path)
            if self.storage_path is not None
            else Path.cwd() / "results"
        )
        effective_eval_config = deepcopy(self.evaluation_env_config)
        self.write_run_manifest(
            self.env_config,
            run_storage / run_name,
            {
                "algorithm": self.algorithm.value,
                "training": self.training.value,
                "iterations": self.iters,
                "env_steps": self.env_steps,
                "training_budget": {
                    "value": self.env_steps if self.env_steps is not None else self.iters,
                    "unit": "sampled_env_steps" if self.env_steps is not None else "training_iterations",
                    "episode_horizon": self.env_config.get("max_steps"),
                },
                "train_batch_size": self.train_batch_size,
                "tune_samples": self.tune_samples,
                "resources": {
                    "num_env_runners_per_trial": self.num_env_runners,
                    "ray_cpus": self.ray_cpus,
                    "max_concurrent_trials": self.max_concurrent_trials,
                },
                "evaluation": EnvConfigHandler._make_config_serializable(
                    effective_eval_config
                ),
            },
        )
        owns_ray = not ray.is_initialized()
        try:
            # Keep Ray setup and Tune execution in one cleanup scope.
            if not ray.is_initialized():
                self._start_ray(self.ray_cpus, self.gpus)

            tuner = Tuner(
                trainable=algo_config.algo_class,
                param_space=algo_config,
                tune_config=TuneConfig(
                    num_samples=self.tune_samples,
                    max_concurrent_trials=self.max_concurrent_trials,
                    trial_dirname_creator=lambda trial: trial.trial_id,
                    scheduler=self._get_tune_scheduler(hyperparam_mutations),
                    metric=f"{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                    mode="max",
                    reuse_actors=False,
                ),
                run_config=RunConfig(
                    storage_path=str(run_storage),
                    verbose=1,
                    name=run_name,
                    # JSON/CSV retain portable, machine-readable Tune results.
                    callbacks=[CSVLoggerCallback(), JsonLoggerCallback()],
                    stop=(
                        {"num_env_steps_sampled_lifetime": self.env_steps}
                        if self.env_steps is not None and not _checkpoint_path
                        else {
                            (
                                "iterations_since_restore"
                                if _checkpoint_path
                                else TRAINING_ITERATION
                            ): self.iters if _iters is None else abs(int(_iters))
                        }
                    )
                    | {DONE: True},
                    checkpoint_config=CheckpointConfig(
                        checkpoint_score_attribute=self._selection_metric(),
                        checkpoint_frequency=self.checkpoint_freq,
                        checkpoint_at_end=True,
                        num_to_keep=3,
                    ),
                ),
            )

            # Execute trials and reject partial Tune failures.
            results = tuner.fit()
            if results.num_errors:
                messages = "; ".join(str(error) for error in results.errors)
                raise RuntimeError(
                    f"Training failed in {results.num_errors} trial(s): {messages}"
                )

            self._save_env_config(results)
            self._save_episode_records(results)

            metrics = self.get_best_metrics(results)

            return results, metrics
        finally:
            # Ensure failed notebook runs do not leave Ray workers alive.
            if (
                owns_ray
                and ray.is_initialized()
                and os.environ.get("MARLEM_KEEP_RAY_ALIVE") != "1"
            ):
                ray.shutdown()

    def restore_experiment(
        self, experiment_path: str, embeddings_dim: int = 128
    ) -> Tuple[ResultGrid, Dict[str, Any]]:
        """Restore tuner from experiment directory to continue training.

        Args:
            experiment_path: Path to the Ray RLlib experiment.
            embeddings_dim: The dimension of the embeddings.

        Returns:
            ResultGrid: The results of the training and evaluation.
            Dict[str, Any]: The metrics of the training and evaluation.
        """
        if not Tuner.can_restore(experiment_path):
            raise ValueError(f"Cannot restore tuner from path: {experiment_path}.")

        # Setup configuration
        algo_config, _ = self._setup_config(embeddings_dim)
        algo_config = self._setup_custom_algo_config(algo_config).algo_config

        try:
            tuner = Tuner.restore(
                path=experiment_path, trainable=algo_config.algo_class
            )

        except Exception as e:
            raise ValueError(
                f"Failed to restore tuner from experiment {experiment_path}: {e}."
            )

        # Initialize ray
        owns_ray = not ray.is_initialized()
        if not ray.is_initialized():
            self._start_ray(self.ray_cpus, self.gpus)

        try:
            # Run the restored tuner and capture the results
            results = tuner.fit()

            # Save environment configuration to experiment directory
            self._save_env_config(results)
            self._save_episode_records(results)

            # Extract metrics from the best result
            metrics = self.get_best_metrics(results)

            return results, metrics
        finally:
            if owns_ray and ray.is_initialized():
                ray.shutdown()

    def train_checkpoint(
        self,
        checkpoint_path: str,
        iters: Optional[int] = None,
        embeddings_dim: int = 128,
    ) -> Tuple[ResultGrid, Dict[str, Any]]:
        """Continue training an RL algorithm from a checkpoint.

        Args:
            checkpoint_path: The path of the checkpoint to restore.
            iters: The number of iterations to train for restored checkpoint.
            embeddings_dim: The dimension of the embeddings.

        Returns:
            ResultGrid: The results of the training and evaluation.
            Dict[str, Any]: The metrics of the training and evaluation.
        """
        return self.train(embeddings_dim, checkpoint_path, iters)

    # endregion

    # region Result selection and reporting
    def _selection_metric(self) -> str:
        """Use held-out return only when a held-out evaluation is configured."""
        base = f"{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}"
        return (
            f"{EVALUATION_RESULTS}/{base}"
            if self.evaluation_interval is not None
            else base
        )

    def get_best_results(
        self, results: ResultGrid
    ) -> Tuple[ResultGrid, Optional[ResultGrid]]:
        """Get the best results of an experiment using as principal metric the
        `episode_return_mean`.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Tuple[ResultGrid, ResultGrid]: The best results of the training and evaluation.
        """
        train = results.get_best_result(
            metric=f"{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}", mode="max"
        )

        eval = None
        if self.evaluation_interval is not None:
            # Short smoke runs can legitimately finish before the first
            # evaluation interval.  Treat missing evaluation metrics as no
            # evaluation checkpoint rather than failing checkpoint selection.
            try:
                eval = results.get_best_result(
                    metric=f"{EVALUATION_RESULTS}/{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                    mode="max",
                )
            except Exception:
                eval = None

        return train, eval

    def get_best_metrics(
        self, results: ResultGrid, as_dataframe: bool = False
    ) -> Dict[str, Any]:
        """Get the metrics for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.
            as_dataframe: Whether to return the metrics as a pandas DataFrame.

        Returns:
            Dict[str, Any]: The training and evaluation metrics of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {
            "train": train.metrics_dataframe if as_dataframe else train.metrics,
            "eval": (eval.metrics_dataframe if as_dataframe else eval.metrics)
            if eval
            else None,
        }

    def get_best_hyperparameters(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the hyperparameters for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation hyperparameters of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.config, "eval": eval.config if eval else None}

    def get_best_experiment(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the path of the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation path of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.path, "eval": eval.path if eval else None}

    def get_best_checkpoint(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the checkpoint for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation checkpoint of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {
            "train": train.checkpoint,
            "eval": (
                eval.checkpoint
                if eval is not None and eval.checkpoint is not None
                else None
            ),
        }

    def get_best_trial(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the trial for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation trial of an experiment.
        """
        # Setup configuration
        _, hyperparam_mutations = self._setup_config()

        # Get the best results
        train, eval = self.get_best_results(results)

        return {
            "train": {
                k: v for k, v in train.config.items() if k in hyperparam_mutations
            },
            "eval": {k: v for k, v in eval.config.items() if k in hyperparam_mutations}
            if eval
            else None,
        }

    # endregion


class GroupedLEM(Env):
    """Expose the multi-agent market as one ordered joint-action environment."""

    # region Grouped environment adapter
    def __init__(self, env_config):
        """Single centralized decision process with an explicitly ordered tuple."""
        super().__init__()
        self.env = LocalEnergyMarket(env_config)
        self.original_agents_id = self.env.agent_order
        self.agents_id = ["grouped_agents"]
        self.agents = list(self.agents_id)
        self.possible_agents = list(self.agents_id)
        self.observation_space = spaces.Dict(
            {
                "grouped_agents": self._dict_to_tuple_space(
                    self.env.observation_spaces, self.original_agents_id
                )
            }
        )
        self.action_space = spaces.Dict(
            {
                "grouped_agents": self._dict_to_tuple_space(
                    self.env.action_spaces, self.original_agents_id
                )
            }
        )

    def reset(self, *, seed=None, options=None):
        """Reset the underlying market and preserve its agent ordering."""
        super().reset(seed=seed)
        observations, infos = self.env.reset(seed=seed, options=options)
        return {
            "grouped_agents": tuple(observations[id] for id in self.original_agents_id)
        }, {"grouped_agents": infos}

    def step(self, action_dict):
        """Unpack one joint action and return a mean group reward."""
        controls = action_dict["grouped_agents"]
        if len(controls) != len(self.original_agents_id):
            raise ValueError("Grouped action count does not match agent ordering.")
        obs, rewards, terminated, truncated, infos = self.env.step(
            dict(zip(self.original_agents_id, controls))
        )
        total, mean = self._aggregate_group_reward(rewards)
        info = dict(self.env.info)
        info.update(
            group_total_reward=total,
            group_mean_reward=mean,
            group_agent_rewards=dict(rewards),
        )
        return (
            {"grouped_agents": tuple(obs[id] for id in self.original_agents_id)},
            mean,
            terminated["__all__"],
            truncated["__all__"],
            info,
        )

    @staticmethod
    def _aggregate_group_reward(rewards: MultiAgentDict) -> Tuple[float, float]:
        total = float(sum(rewards.values()))
        return total, total / len(rewards) if rewards else 0.0

    @staticmethod
    def _dict_to_tuple_space(
        dict_space: spaces.Dict, agent_order: Tuple[str, ...]
    ) -> spaces.Tuple:
        """Converts a gymnasium Dict space to a Tuple space.

        It uses the environment's immutable agent order.

        Args:
            dict_space: The Dict space to convert.

        Returns:
            A Tuple space containing the subspaces from the original Dict.
        """
        if set(dict_space.keys()) != set(agent_order):
            raise ValueError("Agent order does not match the provided spaces.")

        tuple_of_spaces = tuple(dict_space[agent_id] for agent_id in agent_order)

        return spaces.Tuple(tuple_of_spaces)

    def close(self):
        self.env.close()

    # endregion


# region Learner adapter
class GroupedSACTorchLearner(SACTorchLearner):
    """Use SAC's continuous joint-action loss for MARLEM's tuple of Boxes.

    The CTDE/CTCE modules already compute joint Q values and summed Gaussian
    log probabilities. Only stock RLlib's Box-only dispatch needs adapting.
    """

    def compute_loss_for_module(self, *, module_id, config, batch, fwd_out):
        action_space = self.module[module_id].action_space
        if (
            isinstance(action_space, spaces.Dict)
            and set(action_space.spaces) == {"grouped_agents"}
            and isinstance(action_space["grouped_agents"], spaces.Tuple)
            and all(
                isinstance(child, spaces.Box)
                for child in action_space["grouped_agents"]
            )
        ):
            return self._compute_loss_for_module_continuous(
                module_id=module_id, config=config, batch=batch, fwd_out=fwd_out
            )
        return super().compute_loss_for_module(
            module_id=module_id, config=config, batch=batch, fwd_out=fwd_out
        )


# endregion

# region Episode metrics callback


class EpisodeRecordCallback(RLlibCallback):
    """Collect completed episode values in workers and append them on the driver."""

    _returns_key = "raw_episode_returns"
    _lengths_key = "raw_episode_lengths"
    _seeds_key = "raw_episode_seeds"

    @staticmethod
    def _find_info_value(value: Any, key: str) -> Any:
        """Find a value in direct or grouped multi-agent info structures."""
        if isinstance(value, dict):
            if key in value:
                return value[key]
            for nested in value.values():
                found = EpisodeRecordCallback._find_info_value(nested, key)
                if found is not None:
                    return found
        elif isinstance(value, (list, tuple)):
            for nested in reversed(value):
                found = EpisodeRecordCallback._find_info_value(nested, key)
                if found is not None:
                    return found
        return None

    def on_episode_end(
        self, *, episode: Any, metrics_logger: Any = None, **kwargs
    ) -> None:
        if metrics_logger is None:
            return
        episode_return = float(episode.get_return())
        metrics_logger.log_value(
            self._returns_key, episode_return, reduce=None, clear_on_reduce=True
        )
        metrics_logger.log_value(
            self._lengths_key,
            int(episode.env_steps()),
            reduce=None,
            clear_on_reduce=True,
        )
        try:
            infos = episode.get_infos()
            episode_seed = self._find_info_value(infos, "episode_seed")
            if episode_seed is not None:
                metrics_logger.log_value(
                    self._seeds_key,
                    int(episode_seed),
                    reduce=None,
                    clear_on_reduce=True,
                )
            for key in ("group_total_reward", "group_mean_reward"):
                value = self._find_info_value(infos, key)
                if value is not None:
                    metrics_logger.log_value(
                        key,
                        float(value),
                        reduce=None,
                        clear_on_reduce=True,
                    )
        except (AttributeError, TypeError, StopIteration):
            pass


# endregion

# region Optimizer callbacks


class SingleOptimizerCallback(EpisodeRecordCallback):
    """Callback to fix optimizer settings to prevent beta1 Tensor error.

    This callback fixes the "beta1 as a Tensor is not supported for capturable=False
    and foreach=True" error on all optimizers after algorithm initialization and
    checkpoint loading for RLModule.

    Based on: https://github.com/ray-project/ray/issues/51560#issuecomment-2831921054
    """

    def on_checkpoint_loaded(self, *, algorithm: Algorithm, **kwargs) -> None:
        def betas_tensor_to_float(learner: Learner) -> None:
            for optimizer in learner._optimizer_parameters:
                for param_grp in optimizer.param_groups:
                    param_grp["betas"] = tuple(
                        beta.item() if isinstance(beta, Tensor) else beta
                        for beta in param_grp["betas"]
                    )

        algorithm.learner_group.foreach_learner(betas_tensor_to_float)


class MultiOptimizerCallback(EpisodeRecordCallback):
    """Callback to fix optimizer settings to prevent beta1 Tensor error.

    This callback fixes the "beta1 as a Tensor is not supported for capturable=False
    and foreach=True" error on all optimizers after algorithm initialization and
    checkpoint loading for MultiRLModule.

    Based on: https://github.com/ray-project/ray/issues/51560#issuecomment-3173182766
    """

    def on_checkpoint_loaded(self, *, algorithm: Algorithm, **kwargs) -> None:
        def betas_tensor_to_float(learner: Learner) -> None:
            for optimizer in learner._optimizer_parameters:
                for param_grp in optimizer.param_groups:
                    param_grp["betas"] = tuple(
                        beta.item() if isinstance(beta, Tensor) else beta
                        for beta in param_grp["betas"]
                    )

        algorithm.learner_group.foreach_learner(betas_tensor_to_float)


# endregion

# endregion
