"""
Multi-agent reinforcement learning training implementation using Ray RLlib.
"""

import json
from datetime import datetime
from os import cpu_count
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple, Type

import ray
from gymnasium import spaces
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.algorithms.algorithm_config import AlgorithmConfig
from ray.rllib.algorithms.appo import APPOConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.callbacks.callbacks import RLlibCallback
from ray.rllib.core.learner.learner import Learner
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.policy.policy import PolicySpec
from ray.rllib.utils.metrics import ENV_RUNNER_RESULTS, EPISODE_RETURN_MEAN, EVALUATION_RESULTS
from ray.rllib.utils.replay_buffers.replay_buffer import StorageUnit
from ray.rllib.utils.typing import MultiAgentDict
from ray.tune import CheckpointConfig, ResultGrid, RunConfig, TuneConfig, Tuner, loguniform
from ray.tune.result import DONE, TRAINING_ITERATION
from ray.tune.schedulers import PopulationBasedTraining
from torch import Tensor
from torch.cuda import device_count, is_available

from .base import RLAlgorithm, TrainingMode
from .ctce import CTCEModule
from .ctde import CTDEModule
# DEVIATION: the market environment (lem.py, io.py) is not imported. The trainer
# takes the environment class as an argument (`env_class`), so any multi-agent
# environment with the same interface can be trained (see core/envs/).


class RLTrainer:
    """Manages training using Ray RLlib with support for multiple algorithms."""

    def __init__(self,
                 env_class: Type[MultiAgentEnv],
                 env_config: Dict[str, Any],
                 algorithm: RLAlgorithm = RLAlgorithm.PPO,
                 training: TrainingMode = TrainingMode.DTDE,
                 iters: int = 100,
                 tune_samples: int = 1,
                 checkpoint_freq: int = 10,
                 evaluation_interval: int = 1,
                 evaluation_duration: int | Literal["auto"] = "auto",
                 cpus: Optional[int] = None,
                 gpus: Optional[int] = None,
                 storage_path: Optional[str] = None):
        """Initialize the RL trainer.

        Args:
            env_class: The multi-agent environment class, built as
                ``env_class(env_config)``. DEVIATION: the original always used
                ``LocalEnergyMarket``.
            env_config: Environment configuration dictionary
            algorithm: RL algorithm to use (PPO, APPO, SAC)
            training: Training mode (CTCE, CTDE, DTDE)
            iters: Number of training iterations
            tune_samples: Number of samples for tuning
            checkpoint_freq: Frequency of checkpoints
            evaluation_interval: Frequency of evaluation
            evaluation_duration: Duration of evaluation
            cpus: Number of CPUs for parallel sampling
            gpus: Number of GPUs per learner
            storage_path: Path to store training results
        """
        self.env_class = env_class
        self.grouped_env_class = grouped(env_class)
        self.env_config = env_config
        self.algorithm = algorithm
        self.training = training
        self.iters = iters
        self.tune_samples = tune_samples
        self.checkpoint_freq = checkpoint_freq
        self.evaluation_interval = evaluation_interval
        self.evaluation_duration = evaluation_duration
        self.cpus = self._get_cpus_count() if cpus is None else cpus
        self.gpus = self._get_cuda_gpu_count() if gpus is None else gpus
        self.storage_path = storage_path

        # Validate initialization parameters
        self._check_init()

        # Initialize environment
        self.env: MultiAgentEnv = env_class(env_config) if self.training == TrainingMode.DTDE else self.grouped_env_class(env_config)

    def _check_init(self) -> None:
        """Validate initialization parameters to ensure proper configuration."""
        # Validate algorithm
        if not isinstance(self.algorithm, RLAlgorithm):
            raise ValueError(f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC'].")

        # Validate training mode
        if not isinstance(self.training, TrainingMode):
            raise ValueError(f"The <training> must be a TrainingMode enum, got <training = {self.training}>, supported training modes: ['CTCE', 'CTDE', 'DTDE'].")

        # Validate positive integers
        if not isinstance(self.cpus, int) or self.cpus <= 0:
            raise ValueError(f"The <cpus> must be a positive integer, got <cpus = {self.cpus}>.")

        if not isinstance(self.gpus, int) or self.gpus < 0:
            raise ValueError(f"The <gpus> must be a non-negative integer, got <gpus = {self.gpus}>.")

        if not isinstance(self.iters, int) or self.iters <= 0:
            raise ValueError(f"The <iters> must be a positive integer, got <iters = {self.iters}>.")

        if not isinstance(self.tune_samples, int) or self.tune_samples <= 0:
            raise ValueError(f"The <tune_samples> must be a positive integer, got <tune_samples = {self.tune_samples}>.")

        if not isinstance(self.checkpoint_freq, int) or self.checkpoint_freq <= 0:
            raise ValueError(f"The <checkpoint_freq> must be a positive integer, got <checkpoint_freq = {self.checkpoint_freq}>.")

        if not isinstance(self.evaluation_interval, int) or self.evaluation_interval <= 0:
            raise ValueError(f"The <evaluation_interval> must be a positive integer, got <evaluation_interval = {self.evaluation_interval}>.")

        # FAULT I-62: read as (not A) or B, so every integer is rejected; only
        # "auto" passes.
        if not (isinstance(self.evaluation_duration, str) and self.evaluation_duration == "auto") or (isinstance(self.evaluation_duration, int) and self.evaluation_duration <= 0):
            raise ValueError(f"The <evaluation_duration> must be a positive integer or 'auto', got <evaluation_duration = {self.evaluation_duration}>.")

        # Validate checkpoint frequency doesn't exceed iterations
        if self.checkpoint_freq > self.iters:
            raise ValueError(f"The <checkpoint_freq> ({self.checkpoint_freq}) cannot be greater than <iters> ({self.iters}).")

        # Validate storage path if provided
        if self.storage_path is not None:
            storage_path = Path(self.storage_path)
            if not storage_path.parent.exists():
                raise ValueError(f"The storage path parent directory does not exist: <storage_path = {storage_path.parent}>.")

        # Validate environment configuration
        if not isinstance(self.env_config, dict):
            raise ValueError(f"The <env_config> must be a dictionary, got <env_config = {self.env_config}>.")

        # DEVIATION: the market's keys (max_steps, market_config, agents) are
        # checked by the environment itself; here only that it is an environment.
        if not (isinstance(self.env_class, type) and issubclass(self.env_class, MultiAgentEnv)):
            raise ValueError(f"The <env_class> must be a MultiAgentEnv subclass, got <env_class = {self.env_class}>.")

    @staticmethod
    def _get_cpus_count() -> int:
        """
        Get the number of CPUs available.

        Returns:
            int: The number of CPUs available.
        """
        # FAULT I-62: used for sampling and again for evaluation workers, so the
        # CPUs are counted twice (16 processes on a 12-thread machine).
        return max(1, cpu_count() - 4)

    @staticmethod
    def _get_cuda_gpu_count() -> int:
        """
        Get the number of CUDA GPUs available.

        Returns:
            int: The number of CUDA GPUs available.
        """
        return device_count() if is_available() else 0

    def _setup_config(self, embeddings_dim: int = 128) -> Tuple[AlgorithmConfig, Dict[str, Any]]:
        """
        Setup the algorithm configuration based on the specified algorithm type,
        and dynamically select valid hyperparameters for PBT based on algorithm.

        Args:
            embeddings_dim: The dimension of the embeddings.

        Returns:
            Tuple[AlgorithmConfig, Dict[str, Any]]: Tuple containing the algorithm configuration
            and the hyperparameter mutations.
        """
        # Setup the hyperparameter mutations based on the algorithm type
        # FAULT I-49: lr mutates in [1e-4, 1e-2] but starts at 1e-5, so the first
        # resample jumps it 10-1000x; entropy_coeff can reach 10 (1000x its start),
        # which makes CTCE and CTDE diverge (R-01).
        if self.algorithm == RLAlgorithm.PPO:
            hyperparam_mutations = {"lr": loguniform(0.0001, 0.01),
                                    "entropy_coeff": loguniform(0.01, 10.0),
                                    "lambda_": loguniform(0.8, 0.99),
                                    # "clip_param": loguniform(0.1, 0.3),
            }

        elif self.algorithm == RLAlgorithm.APPO:
            hyperparam_mutations = {"lr": loguniform(0.0001, 0.01),
                                    "entropy_coeff": loguniform(0.01, 10.0),
                                    "lambda_": loguniform(0.8, 0.99)}

        elif self.algorithm == RLAlgorithm.SAC:
            hyperparam_mutations = {"actor_lr": loguniform(0.0001, 0.01),
                                    "critic_lr": loguniform(0.0001, 0.01),
                                    # "tau": loguniform(0.001, 0.01),  # Soft update, if configurable
            }

        else:
            raise ValueError(f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC'].")

        # Setup the complete configuration
        config = self._setup_algorithm_config()
        config = self._setup_extra_config(config)
        config = self._setup_training_config(config, embeddings_dim)

        return config, hyperparam_mutations

    def _setup_algorithm_config(self) -> AlgorithmConfig:
        """
        Setup the algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration.
        """
        if self.algorithm == RLAlgorithm.PPO:
            # FAULT R-02: kl_coeff=0.0 does not switch the KL term off (use_kl_loss
            # stays True): an infinite KL gives 0 * inf = NaN loss, and RLlib zeroes the
            # NaN gradients and keeps training.
            return (PPOConfig()
                    .training(lr=1e-5,
                              gamma=0.99,
                              use_critic=True,
                              use_gae=True,
                              lambda_=0.95,
                              num_epochs=30,
                              minibatch_size=128,
                              kl_coeff=0.0,
                              entropy_coeff=0.01,
                              clip_param=0.2,
                              grad_clip=0.5))

        elif self.algorithm == RLAlgorithm.APPO:
            return (APPOConfig()
                    .training(lr=1e-5,
                              vtrace=True,
                              lambda_=0.95,
                              kl_coeff=0.0,
                              entropy_coeff=0.01,
                              grad_clip=0.5))

        elif self.algorithm == RLAlgorithm.SAC:
            if self.training in [TrainingMode.CTCE, TrainingMode.CTDE]:
                # For centralized modes: sum all agents' action dimensions
                # FAULT R-04: the target is for a squashed Gaussian; CTCE and CTDE give SAC
                # an unsquashed one whose samples are clipped afterwards.
                target_entropy = -sum(space.shape[0] for space in self.env.action_space["grouped_agents"])
                replay_buffer_type = "EpisodeReplayBuffer"
            else:
                # For decentralized mode: each agent has individual action space
                target_entropy = -self.env.action_spaces[self.env.agents_id[0]].shape[0]
                replay_buffer_type = "MultiAgentEpisodeReplayBuffer"

            return (SACConfig()
                    .training(actor_lr=1e-5,
                              critic_lr=1e-5,
                              gamma=0.99,
                              twin_q=True,
                              target_entropy=target_entropy,
                              grad_clip=0.5,
                              replay_buffer_config={"type": replay_buffer_type,
                                                    "capacity": int(1e3),
                                                    "replay_sequence_length": 1,
                                                    "replay_burn_in": 0,
                                                    "replay_zero_init_states": True})
                    .env_runners(batch_mode="complete_episodes"))

        else:
            raise ValueError(f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC'].")

    def _setup_extra_config(self, config: AlgorithmConfig) -> AlgorithmConfig:
        """
        Setup the extra configuration.

        Args:
            config: The algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration with the extra configuration.
        """
        if self.algorithm == RLAlgorithm.PPO:
            evaluation_config = PPOConfig.overrides(exploration=False)
        elif self.algorithm == RLAlgorithm.APPO:
            evaluation_config = APPOConfig.overrides(exploration=False)
        elif self.algorithm == RLAlgorithm.SAC:
            evaluation_config = SACConfig.overrides(exploration=False)
        else:
            raise ValueError(f"The <algorithm> must be an RLAlgorithm enum, got <algorithm = {self.algorithm}>, supported algorithms: ['PPO', 'APPO', 'SAC'].")

        return (config
                .framework("torch")
                # FAULT I-62: self.cpus sampling workers plus self.cpus evaluation workers
                # (below), each loading torch.
                # DECIDE I-72: evaluation runs on the training scenario, with no held-out
                # seeds or days.
                .env_runners(num_env_runners=self.cpus,
                             sample_timeout_s=None)
                .learners(num_learners=1,
                          num_gpus_per_learner=self.gpus)
                .evaluation(evaluation_interval=self.evaluation_interval,
                            evaluation_duration=self.evaluation_duration,
                            evaluation_duration_unit=StorageUnit.EPISODES,
                            evaluation_num_env_runners=self.cpus,
                            evaluation_parallel_to_training=True,
                            evaluation_config=evaluation_config))

    def _setup_training_config(self,
                               config: AlgorithmConfig,
                               embeddings_dim: int = 128) -> AlgorithmConfig:
        """
        Setup the training mode configuration.

        Args:
            config: The algorithm configuration.
            embeddings_dim: The dimension of the embeddings.

        Returns:
            AlgorithmConfig: The algorithm configuration with the mode configuration.
        """
        if self.training == TrainingMode.CTCE:
            return (config
                    .environment(self.grouped_env_class,
                                 env_config=self.env_config)
                    .rl_module(rl_module_spec=RLModuleSpec(module_class=CTCEModule,
                                                           observation_space=self.env.observation_space,
                                                           action_space=self.env.action_space,
                                                           model_config={"algorithm": self.algorithm.value,
                                                                         "embeddings_dim": embeddings_dim}))
                    .callbacks(MultiOptimizerCallback))

        elif self.training == TrainingMode.CTDE:
            return (config
                    .environment(self.grouped_env_class,
                                 env_config=self.env_config)
                    .rl_module(rl_module_spec=RLModuleSpec(module_class=CTDEModule,
                                                           observation_space=self.env.observation_space,
                                                           action_space=self.env.action_space,
                                                           model_config={"algorithm": self.algorithm.value,
                                                                         "agents_id": self.env.original_agents_id,
                                                                         "embeddings_dim": embeddings_dim}))
                    .callbacks(MultiOptimizerCallback))

        elif self.training == TrainingMode.DTDE:
            # Setup the policy of each agent
            agents_policy = {agent_id: PolicySpec(observation_space=self.env.observation_spaces[agent_id],
                                                  action_space=self.env.action_spaces[agent_id])
                             for agent_id in self.env.agents_id}

            # Setup the RL module of each agent
            # FAULT R-03: DTDE gets RLlib's default network (2 x 256 tanh, log_std
            # clipped); CTCE and CTDE a custom 2 x 128 ReLU one without the clip.
            agents_rl_module = {agent_id: RLModuleSpec(module_class=self.algorithm.get_module_class(),
                                                       observation_space=agents_policy[agent_id].observation_space,
                                                       action_space=agents_policy[agent_id].action_space)
                                for agent_id in self.env.agents_id}

            return (config
                    .environment(self.env_class,
                                 env_config=self.env_config)
                    .multi_agent(policies=agents_policy,
                                 policy_mapping_fn=lambda agent_id, *args, **kwargs: agent_id)
                    .rl_module(rl_module_spec=MultiRLModuleSpec(rl_module_specs=agents_rl_module))
                    .callbacks(SingleOptimizerCallback))

        else:
            raise ValueError(f"The <training> must be a TrainingMode enum, got <training = {self.training}>, supported training modes: ['CTCE', 'CTDE', 'DTDE'].")

    def _setup_custom_algo_config(self, config: AlgorithmConfig) -> AlgorithmConfig:
        """
        Setup the custom algorithm config.

        Args:
            config: The algorithm configuration.

        Returns:
            AlgorithmConfig: The algorithm configuration with the custom algorithm config.
        """
        class CustomAlgorithm(PPOConfig if self.algorithm == RLAlgorithm.PPO else APPOConfig if self.algorithm == RLAlgorithm.APPO else SACConfig):
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

    def _save_env_config(self, results: ResultGrid) -> None:
        """Save environment configuration to experiment directory.

        Args:
            results: The results of the training and evaluation.
        """
        # DEVIATION: plain JSON instead of the market's EnvConfigHandler; values
        # JSON cannot hold are written as text.
        folder = Path(results.get_best_result().path).parent
        with open(folder / "env_config.json", "w", encoding="utf-8") as f:
            json.dump({"env_class": self.env_class.__name__, **self.env_config}, f, indent=2, default=str)

    def train(self,
              embeddings_dim: int = 128,
              _checkpoint_path: Optional[str] = None,
              _iters: Optional[int] = None) -> Tuple[ResultGrid, Dict[str, Any]]:
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
        # Setup configuration
        algo_config, hyperparam_mutations = self._setup_config(embeddings_dim)
        # algo_config = self._setup_custom_algo_config(algo_config).algo_config

        if _checkpoint_path:
            algo_config.callbacks(on_algorithm_init=lambda algorithm, **kwargs: algorithm.restore_from_path(_checkpoint_path))

        # FAULT I-62: ray.shutdown() at the end is not in a finally, so a failed
        # run leaves Ray running.
        # FAULT I-64: one seed per trial, no random or untrained baseline, no
        # manifest of versions and settings.
        # Initialize ray
        if not ray.is_initialized():
            ray.init()

        # Initialize the tuner
        tuner = Tuner(trainable=algo_config.algo_class,
                      param_space=algo_config,
                      tune_config=TuneConfig(num_samples=self.tune_samples,
                                             # FAULT I-62: population-based training is always on, also for one trial.
                                             scheduler=PopulationBasedTraining(time_attr=TRAINING_ITERATION,
                                                                               perturbation_interval=self.checkpoint_freq,
                                                                               hyperparam_mutations=hyperparam_mutations),
                                             metric=f"{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                                             mode="max",
                                             reuse_actors=False),
                      run_config=RunConfig(storage_path=self.storage_path,
                                           name=f"{self.env_class.__name__.lower()}_{self.algorithm.value}_{self.training.value}_{datetime.now().strftime('%Y%m%d%H%M')}",
                                           # DECIDE I-50: the budget is in training iterations; [P2] trains
                                           # "10 000 episodes".
                                           stop={TRAINING_ITERATION: self.iters if _iters is None else abs(int(_iters)),
                                                 #  "time_total_s": None,
                                                 DONE: True},
                                           checkpoint_config=CheckpointConfig(checkpoint_score_attribute=f"{EVALUATION_RESULTS}/{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                                                                              checkpoint_frequency=self.checkpoint_freq,
                                                                              checkpoint_at_end=True,
                                                                              num_to_keep=3)))

        # Run the tuner and capture the results
        results = tuner.fit()

        # Save environment configuration
        self._save_env_config(results)

        # Extract metrics from the best result
        metrics = self.get_best_metrics(results)

        # Shutdown ray
        ray.shutdown()

        return results, metrics

    def restore_experiment(self,
                           experiment_path: str,
                           embeddings_dim: int = 128) -> Tuple[ResultGrid, Dict[str, Any]]:
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
            tuner = Tuner.restore(path=experiment_path,
                                  trainable=algo_config.algo_class)

        except Exception as e:
            raise ValueError(f"Failed to restore tuner from experiment {experiment_path}: {e}.")

        # Initialize ray
        if not ray.is_initialized():
            ray.init()

        # FAULT I-62: ray.shutdown() below is not in a finally.
        # Run the restored tuner and capture the results
        results = tuner.fit()

        # Save environment configuration to experiment directory
        self._save_env_config(results)

        # Extract metrics from the best result
        metrics = self.get_best_metrics(results)

        # Shutdown ray
        ray.shutdown()

        return results, metrics

    def train_checkpoint(self,
                         checkpoint_path: str,
                         iters: Optional[int] = None,
                         embeddings_dim: int = 128) -> Tuple[ResultGrid, Dict[str, Any]]:
        """Continue training an RL algorithm from a checkpoint.

        Args:
            checkpoint_path: The path of the checkpoint to restore.
            iters: The number of iterations to train for restored checkpoint.
            embeddings_dim: The dimension of the embeddings.

        Returns:
            ResultGrid: The results of the training and evaluation.
            Dict[str, Any]: The metrics of the training and evaluation.
        """
        return self.train(embeddings_dim,
                          checkpoint_path,
                          iters)

    @staticmethod
    def get_best_results(results: ResultGrid) -> Tuple[ResultGrid, ResultGrid]:
        """Get the best results of an experiment using as principal metric the
        `episode_return_mean`.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Tuple[ResultGrid, ResultGrid]: The best results of the training and evaluation.
        """
        train = results.get_best_result(metric=f"{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                                        mode="max")

        eval = results.get_best_result(metric=f"{EVALUATION_RESULTS}/{ENV_RUNNER_RESULTS}/{EPISODE_RETURN_MEAN}",
                                       mode="max")

        return train, eval

    def get_best_metrics(self,
                         results: ResultGrid,
                         as_dataframe: bool = False) -> Dict[str, Any]:
        """Get the metrics for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.
            as_dataframe: Whether to return the metrics as a pandas DataFrame.

        Returns:
            Dict[str, Any]: The training and evaluation metrics of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.metrics_dataframe if as_dataframe else train.metrics,
                "eval": eval.metrics_dataframe if as_dataframe else eval.metrics}

    def get_best_hyperparameters(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the hyperparameters for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation hyperparameters of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.config,
                "eval": eval.config}

    def get_best_experiment(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the path of the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation path of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.path,
                "eval": eval.path}

    def get_best_checkpoint(self, results: ResultGrid) -> Dict[str, Any]:
        """Get the checkpoint for the best result of an experiment.

        Args:
            results: The results of an Ray Tune experiment.

        Returns:
            Dict[str, Any]: The training and evaluation checkpoint of an experiment.
        """
        train, eval = self.get_best_results(results)

        return {"train": train.checkpoint,
                "eval": eval.checkpoint}

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

        return {"train": {k: v for k, v in train.config.items() if k in hyperparam_mutations},
                "eval": {k: v for k, v in eval.config.items() if k in hyperparam_mutations}}


class GroupedEnv(MultiAgentEnv):
    """
    Grouped environment: all agents of ``env_class`` as one agent, for CTCE and
    CTDE. DEVIATION: was ``GroupedLEM``, fixed to the local energy market; build a
    subclass for any environment with ``grouped(env_class)``.
    """

    env_class: Type[MultiAgentEnv]

    def __init__(self, env_config: Dict[str, Any]) -> None:
        """Initialize the grouped environment.

        Args:
            env_config: Environment configuration dictionary
        """
        super().__init__()

        # Multi-agent environment
        env = self.env_class(env_config)

        _tuple_obs_space = self._dict_to_tuple_space(env.observation_spaces)
        _tuple_act_space = self._dict_to_tuple_space(env.action_spaces)

        # Original `agents_id`
        self.original_agents_id = env.agents_id

        # Grouped environment
        # FAULT I-59: RLlib packs the grouped data in env.agents_id order, but the
        # grouped spaces are in sorted name order (_dict_to_tuple_space): with names
        # like agent_1 ... agent_10 an agent's action is scaled to another's bounds.
        self.env = env.with_agent_groups(groups={"grouped_agents": env.agents_id},
                                         obs_space=_tuple_obs_space,
                                         act_space=_tuple_act_space)
        self.agents_id = ["grouped_agents"]
        self.agents = self.possible_agents = self.agents_id
        self.observation_space = spaces.Dict({"grouped_agents": _tuple_obs_space})
        self.action_space = spaces.Dict({"grouped_agents": _tuple_act_space})

    def reset(self,
              *,
              seed: Optional[int] = None,
              options: Optional[Dict] = None) -> Tuple[MultiAgentDict, MultiAgentDict]:
        """Reset the environment.

        Args:
            seed: The seed for the environment.
            options: The options for the environment.

        Returns:
            obs, infos = self.env.reset(seed, options)
        """
        # Reset the environment
        obs, infos = self.env.reset(seed=seed,
                                    options=options)

        # Pack the observations into a group
        grouped_obs = {k: tuple(v) for k, v in obs.items()}

        return grouped_obs, infos

    def step(self, action_dict: MultiAgentDict) -> Tuple[MultiAgentDict, float, bool, bool, MultiAgentDict]:
        # Unpack the actions from the group to individual agent actions
        obs, rewards, terminateds, truncateds, infos = self.env.step(action_dict)

        # Pack the observations into a group
        grouped_obs = {k: tuple(v) for k, v in obs.items()}

        # The reward for the group is the sum of individual rewards
        # FAULT I-60: CTCE learns every agent's action from this sum, so it learns
        # more slowly: a baseline, not an upper bound as [P1] and [P2] call it.
        # DECIDE I-73: CTCE/CTDE optimise the sum, DTDE per-agent returns; [P2]
        # ranks them by one undefined "mean episode reward".
        grouped_reward = sum(rewards.values())

        return grouped_obs, grouped_reward, terminateds["__all__"], truncateds["__all__"], infos

    @staticmethod
    def _dict_to_tuple_space(dict_space: spaces.Dict) -> spaces.Tuple:
        """Converts a gymnasium Dict space to a Tuple space.

        It sorts the dictionary keys to ensure the resulting tuple has a
        consistent order.

        Args:
            dict_space: The Dict space to convert.

        Returns:
            A Tuple space containing the subspaces from the original Dict.
        """
        # Sort keys to ensure the order of spaces is always the same
        # FAULT I-59: sorted name order, not the env.agents_id order of the data.
        sorted_keys = sorted(dict_space.keys())

        # Create a tuple of the subspaces in the sorted order
        tuple_of_spaces = tuple(dict_space[key] for key in sorted_keys)

        return spaces.Tuple(tuple_of_spaces)


def grouped(env_class: Type[MultiAgentEnv]) -> Type[GroupedEnv]:
    """The grouped version of ``env_class`` (a ``GroupedEnv`` subclass).

    DEVIATION: new; RLlib builds environments from a class and a config, so the
    wrapped class is fixed in a subclass rather than passed in the config.
    """
    return type(f"Grouped{env_class.__name__}", (GroupedEnv,), {"env_class": env_class})


class SingleOptimizerCallback(RLlibCallback):
    """Callback to fix optimizer settings to prevent beta1 Tensor error.

    This callback fixes the "beta1 as a Tensor is not supported for capturable=False
    and foreach=True" error on all optimizers after algorithm initialization and
    checkpoint loading for RLModule.

    Based on: https://github.com/ray-project/ray/issues/51560#issuecomment-2831921054
    """
    def on_checkpoint_loaded(self,
                             *,
                             algorithm: Algorithm,
                             **kwargs) -> None:
        def betas_tensor_to_float(learner: Learner) -> None:
            param_grp = next(iter(learner._optimizer_parameters.keys())).param_groups[0]

            if not param_grp["capturable"] and isinstance(param_grp["betas"][0], Tensor):
                param_grp["betas"] = tuple(beta.item() for beta in param_grp["betas"])

        algorithm.learner_group.foreach_learner(betas_tensor_to_float)


class MultiOptimizerCallback(RLlibCallback):
    """Callback to fix optimizer settings to prevent beta1 Tensor error.

    This callback fixes the "beta1 as a Tensor is not supported for capturable=False
    and foreach=True" error on all optimizers after algorithm initialization and
    checkpoint loading for MultiRLModule.

    Based on: https://github.com/ray-project/ray/issues/51560#issuecomment-3173182766
    """
    def on_checkpoint_loaded(self,
                             *,
                             algorithm: Algorithm,
                             **kwargs) -> None:
        def betas_tensor_to_float(learner: Learner) -> None:
            for param_grp_key in learner._optimizer_parameters.keys():
                param_grp = param_grp_key.param_groups[0]
                param_grp["betas"] = tuple(beta.item() for beta in param_grp["betas"])

        algorithm.learner_group.foreach_learner(betas_tensor_to_float)
