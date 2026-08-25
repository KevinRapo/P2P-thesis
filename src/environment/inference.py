"""
Multi-agent reinforcement learning inference implementation using Ray RLlib.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import ray
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.core import Columns
from ray.rllib.env.multi_agent_env import MultiAgentEnv
import torch

from .lem import LocalEnergyMarket
from .train import GroupedLEM


class RLInference:
    """Manages training using Ray RLlib with support for multiple algorithms."""

    def __init__(self,
                 env_config: Dict[str, Any],
                 exploration: bool = False,
                 checkpoint_path: Optional[str] = None,
                 storage_path: Optional[str] = None):
        """Initialize the RL trainer.

        Args:
            env_config: Environment configuration dictionary
            exploration: Whether to use stochastic actions
            checkpoint_path: Path to trained experiment checkpoint
            storage_path: Path to store training results
        """
        self.env_config = env_config
        self.exploration = exploration
        self.checkpoint_path = checkpoint_path
        self.storage_path = storage_path

        # Validate initialization parameters
        self._check_init()

        # Restore the complete Algorithm so evaluation uses its registered
        # connectors and action distribution rather than a local approximation.
        self._owns_ray = not ray.is_initialized()
        self.algorithm: Algorithm = self._restore_from_checkpoint(checkpoint_path)

        # Initialize environment
        env_class = self.algorithm.config.env
        self._grouped = env_class is GroupedLEM or getattr(env_class, "__name__", None) == "GroupedLEM"
        self.env: MultiAgentEnv = GroupedLEM(env_config) if self._grouped else LocalEnergyMarket(env_config)

    def _check_init(self) -> None:
        """Validate initialization parameters to ensure proper configuration."""
        # Validate checkpoint path if provided
        if self.checkpoint_path is None:
            raise ValueError("No checkpoint provided to restore the RL module. Please provide <checkpoint_path>.")

        if self.checkpoint_path is not None:
            checkpoint_path = Path(self.checkpoint_path)
            if not checkpoint_path.parent.exists():
                raise ValueError(f"The <checkpoint_path> parent directory does not exist: <{checkpoint_path.parent}>.")

        # Validate storage path if provided
        if self.storage_path is not None:
            storage_path = Path(self.storage_path)
            if not storage_path.parent.exists():
                raise ValueError(f"The <storage_path> parent directory does not exist: <{storage_path.parent}>.")

        # Validate environment configuration
        if not isinstance(self.env_config, dict):
            raise ValueError(f"The <env_config> must be a dictionary, got <env_config = {self.env_config}>.")

        # Check required environment configuration keys
        for key in ["max_steps", "market_config", "agents"]:
            if key not in self.env_config:
                raise ValueError(f"The <env_config> is missing the required key: <key = {key}>.")

        # Validate max_steps
        if not isinstance(self.env_config["max_steps"], int) or self.env_config["max_steps"] <= 0:
            raise ValueError(f"The <max_steps> must be a positive integer, got <max_steps = {self.env_config["max_steps"]}>.")

        # Validate agents
        if not isinstance(self.env_config["agents"], list) or len(self.env_config["agents"]) == 0:
            raise ValueError(f"The <agents> must be a non-empty list, got <agents = {self.env_config["agents"]}>.")

    def _restore_from_checkpoint(self, checkpoint_path: str) -> Algorithm:
        """Restore the complete RLlib Algorithm for inference.

        Args:
            checkpoint_path: Path to the checkpoint
        """
        try:
            return Algorithm.from_checkpoint(checkpoint_path)
        except Exception as e:
            raise RuntimeError(f"Failed to restore the RLlib Algorithm from experiment <{checkpoint_path}>: {e}.") from e

    def inference(self, iters: int = 10) -> Dict[str, float]:
        """Inference of a trained policy.

        Args:
            iters: Number of inference episodes.

        Returns:
            Dictionary of inference metrics.
        """
        # Validate iters
        if not isinstance(iters, int) or iters <= 0:
            raise ValueError(f"The <iters> must be a positive integer, got <iters = {iters}>.")

        # Metrics to track
        total_rewards = {}
        episode_lengths = []
        price_history = []
        volume_history = []
        grid_balance_history = []
        dso_stats_history = []

        # Inference
        for episode in range(iters):
            print(f"Running episode {episode + 1}/{iters} (RLlib Algorithm inference)")

            # STEP 1. Reset environment
            obs, info = self.env.reset()

            # STEP 2. Initialize episode tracking
            episode_rewards = {agent_id: 0.0 for agent_id in obs.keys()}
            episode_step = 0
            done = False

            # STEP 3. Run episode
            while not done:
                # STEP 4. Use the Algorithm's supported inference path.
                actions = self._compute_actions(obs)

                # STEP 5. Step environment
                obs, rewards, terminateds, truncateds, info = self.env.step(actions)

                # STEP 6. Update episode rewards
                if isinstance(rewards, dict):
                    for agent_id, reward in rewards.items():
                        episode_rewards[agent_id] += reward
                else:
                    episode_rewards["grouped_agents"] = episode_rewards.get("grouped_agents", 0.0) + rewards

                # STEP 7. Track metrics
                episode_info = self._episode_info(info)
                if episode_info:
                    price_history.append(episode_info.get("market_price", 0.0))
                    volume_history.append(episode_info.get("market_volume", 0.0))
                    grid_balance_history.append(episode_info.get("grid_balance", 0.0))
                    if "dso_stats" in episode_info:
                        dso_stats_history.append(episode_info["dso_stats"])

                # STEP 8. Check termination
                episode_step += 1
                if isinstance(terminateds, dict):
                    done = terminateds.get("__all__", False) or truncateds.get("__all__", False)
                else:
                    done = terminateds or truncateds

                # STEP 9. Check termination
                done = done or episode_step >= self.env_config["max_steps"]

                if done:
                    print(f"Episode {episode + 1} | Done: {done} | Reward = {episode_rewards}")
                    obs, info = self.env.reset()
                    break

            # STEP 10. Record episode metrics
            for agent_id, reward in episode_rewards.items():
                if agent_id not in total_rewards:
                    total_rewards[agent_id] = []
                total_rewards[agent_id].append(reward)

            episode_lengths.append(episode_step)

        return self._calculate_metrics(total_rewards,
                                       episode_lengths,
                                       price_history,
                                       volume_history,
                                       grid_balance_history,
                                       dso_stats_history)

    def close(self) -> None:
        """Release checkpoint workers; only stop Ray when this instance started it."""
        self.algorithm.stop()
        if self._owns_ray and ray.is_initialized():
            ray.shutdown()

    def _compute_actions(self, observations: Dict[str, Any]) -> Dict[str, Any]:
        """Return actions from the restored Algorithm's registered RLModules.

        Ray's new API stack no longer exposes legacy Policy objects through
        ``compute_single_action``. The registered module and its distribution
        remain the authoritative evaluation path, so no local distribution
        parameters or agent ordering are reconstructed here.
        """
        if self._grouped:
            return {"grouped_agents": self._module_action(
                self.algorithm.get_module(), observations["grouped_agents"], grouped=True)}
        return {agent_id: self._module_action(self.algorithm.get_module(agent_id), observation)
                for agent_id, observation in observations.items()}

    def _module_action(self, module: Any, observation: Any, grouped: bool = False) -> Any:
        """Sample an action using the module's own registered distribution class."""
        if module is None:
            raise RuntimeError("The restored Algorithm does not contain the requested policy module.")
        if grouped:
            batched_observation = {"grouped_agents": tuple(
                torch.as_tensor(item, dtype=torch.float32).unsqueeze(0) for item in observation)}
        else:
            batched_observation = torch.as_tensor(observation, dtype=torch.float32).unsqueeze(0)
        forward = module.forward_exploration if self.exploration else module.forward_inference
        output = forward({Columns.OBS: batched_observation})
        distribution = module.get_exploration_action_dist_cls().from_logits(
            output[Columns.ACTION_DIST_INPUTS]) if self.exploration else \
            module.get_inference_action_dist_cls().from_logits(output[Columns.ACTION_DIST_INPUTS])
        sampled = distribution.sample() if self.exploration else distribution.to_deterministic().sample()
        return self._unbatch_action(sampled)

    @staticmethod
    def _unbatch_action(action: Any) -> Any:
        """Convert a one-item Torch action batch back to the environment action shape."""
        if isinstance(action, dict):
            return {name: RLInference._unbatch_action(value) for name, value in action.items()}
        if isinstance(action, tuple):
            return tuple(RLInference._unbatch_action(value) for value in action)
        if isinstance(action, torch.Tensor):
            return action.squeeze(0).detach().cpu().numpy()
        return action

    @staticmethod
    def _episode_info(info: Any) -> Dict[str, Any]:
        """Extract the shared LocalEnergyMarket info record from an API envelope."""
        if not isinstance(info, dict):
            return {}
        if "market_price" in info:
            return info
        return next((value for value in info.values()
                     if isinstance(value, dict) and "market_price" in value), {})

    def _calculate_metrics(self,
                           total_rewards: Dict,
                           episode_lengths: list,
                           price_history: list,
                           volume_history: list,
                           grid_balance_history: list,
                           dso_stats_history: list) -> Dict[str, float]:
        """Calculate comprehensive evaluation metrics."""
        metrics = {}

        # Agent-specific metrics
        for agent_id, rewards in total_rewards.items():
            if rewards:  # Only calculate if we have data
                metrics[f"{agent_id}_mean_reward"] = np.mean(rewards)
                metrics[f"{agent_id}_std_reward"] = np.std(rewards)
                metrics[f"{agent_id}_min_reward"] = np.min(rewards)
                metrics[f"{agent_id}_max_reward"] = np.max(rewards)

        # Overall metrics
        all_rewards = [reward for rewards in total_rewards.values() for reward in rewards]
        if all_rewards:
            metrics["mean_reward"] = np.mean(all_rewards)
            metrics["std_reward"] = np.std(all_rewards)
            metrics["min_reward"] = np.min(all_rewards)
            metrics["max_reward"] = np.max(all_rewards)

        # Episode metrics
        if episode_lengths:
            metrics["mean_episode_length"] = np.mean(episode_lengths)
            metrics["std_episode_length"] = np.std(episode_lengths)

        # Market metrics
        if price_history:
            metrics["mean_price"] = np.mean(price_history)
            metrics["std_price"] = np.std(price_history)
        if volume_history:
            metrics["mean_volume"] = np.mean(volume_history)
            metrics["std_volume"] = np.std(volume_history)
        if grid_balance_history:
            metrics["mean_grid_balance"] = np.mean(np.abs(grid_balance_history))
            metrics["std_grid_balance"] = np.std(grid_balance_history)

        # DSO metrics
        if dso_stats_history:
            try:
                metrics["mean_dso_trade_ratio"] = np.mean([stats["dso_trade_ratio"] for stats in dso_stats_history])
                metrics["mean_dso_volume"] = np.mean([stats["dso_total_volume"] for stats in dso_stats_history])
                metrics["mean_p2p_volume"] = np.mean([stats["p2p_volume"] for stats in dso_stats_history])
            except (KeyError, TypeError):
                # Handle case where dso_stats structure is different
                pass

        return metrics
