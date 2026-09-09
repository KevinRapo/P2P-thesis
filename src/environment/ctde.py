"""
A custom RLModule for Centralized Training, Decentralized Execution (CTDE)
with PPO, APPO, and SAC.
"""

from typing import Any, List, Optional, Tuple

import torch
from ray.rllib.algorithms.sac.sac_learner import QF_PREDS, QF_TWIN_PREDS
from ray.rllib.core import Columns
from ray.rllib.core.distribution.torch.torch_distribution import TorchDiagGaussian, TorchMultiDistribution, TorchSquashedGaussian
from ray.rllib.core.learner.utils import make_target_network
from ray.rllib.core.rl_module.apis import TARGET_NETWORK_ACTION_DIST_INPUTS, QNetAPI, TargetNetworkAPI, ValueFunctionAPI
from ray.rllib.core.rl_module.torch import TorchRLModule
from ray.rllib.policy.sample_batch import SampleBatch
from ray.rllib.utils.annotations import override
from ray.rllib.utils.typing import NetworkType, StateDict, TensorType

from .base import RLAlgorithm


# TorchDiagGaussian interprets the second half of each action-logit vector as
# log standard deviations.  Leaving those values completely unconstrained lets
# a small PPO batch drive ``exp(log_std)`` to infinity, producing invalid KLs
# and gradients before the policy has learned anything.
_LOG_STD_MIN = -5.0
_LOG_STD_MAX = 2.0


class CTDEModule(TorchRLModule, ValueFunctionAPI, TargetNetworkAPI, QNetAPI):
    """
    A custom RLModule for Centralized Training, Decentralized Execution (CTDE).
    with PPO, APPO, and SAC.
    """
    @override(TorchRLModule)
    def setup(self):
        """Initializes the neural networks for the CTDE module."""
        # Get attributes from model_config
        self.algorithm = self.model_config["algorithm"]
        self.agents_id = self.model_config["agents_id"]
        embeddings_dim = self.model_config["embeddings_dim"]

        # Get the observation and action space (both are Dict({"grouped_agents": Tuple(...)}))
        tuple_obs_space = self.observation_space["grouped_agents"]
        tuple_act_space = self.action_space["grouped_agents"]

        if len(tuple_act_space) != len(self.agents_id):
            raise ValueError(f"Number of agents ({len(self.agents_id)}) does not match number of action spaces ({len(tuple_act_space)})")

        # The observation/action space is the concatenated observations/actions of all agents
        concat_obs_dim = sum(space.shape[0] for space in tuple_obs_space)
        concat_act_dim = sum(space.shape[0] for space in tuple_act_space)

        # CTDE has decentralized actors and a centralized critic.  The same
        # local actors are used by execution and by the learner's policy loss;
        # only the critic is allowed to see the concatenated global state.
        self.pi_heads  = torch.nn.ModuleDict({
            agent_id: self._get_network(input_dim=tuple_obs_space[i].shape[0],
                                        output_dim=tuple_act_space[i].shape[0] * 2,  # action_dim * 2 for TorchDiagGaussian (i.e., mean + log_std)
                                        embedding_dim=embeddings_dim)
            for i, agent_id in enumerate(self.agents_id)})
        self.vf_encoder = self._get_encoder_network(concat_obs_dim, embeddings_dim)
        self.vf_head = self._get_head_network(embeddings_dim, 1)

        if self.algorithm == RLAlgorithm.SAC.value:
            # RLlib's stock SAC learner groups actor parameters through the
            # conventional ``pi_encoder``/``pi`` attributes.  Expose the
            # decentralized heads through that interface without introducing
            # another actor (the identity has no trainable parameters).
            self.pi_encoder = torch.nn.Identity()
            self.pi = self.pi_heads
            # Input to Q-networks is [concat_obs_dim, concat_act_dim]
            qf_encoder_input_dim = concat_obs_dim + concat_act_dim

            # Q-networks encoders for embeddings
            self.qf_encoder = self._get_encoder_network(qf_encoder_input_dim, embeddings_dim)
            self.qf_twin_encoder = self._get_encoder_network(qf_encoder_input_dim, embeddings_dim)

            # Q-networks heads for action logits
            self.qf = self._get_head_network(embeddings_dim, 1)
            self.qf_twin = self._get_head_network(embeddings_dim, 1)

        # For a tuple action space, Ray RLlib needs to know how to split the flat action_logits tensor
        self.action_dist_cls = self._get_distribution_class()

    @override(TorchRLModule)
    def _forward_inference(self,
                           batch: SampleBatch,
                           **kwargs) -> StateDict:
        """The decentralized forward pass for inference (exploitation).

        Args:
            batch: The batch received in the forward pass.

        Returns:
            A dictionary with action logits. The learner will use these
            to create the action distribution.
        """
        obs_tuple = batch[Columns.OBS]["grouped_agents"]
        action_logits = [
            self._stabilize_action_logits(self.pi_heads[agent_id](obs_tuple[i]))
            for i, agent_id in enumerate(self.agents_id)
        ]

        return {Columns.ACTION_DIST_INPUTS: torch.cat(action_logits, dim=-1)}

    @override(TorchRLModule)
    def _forward_exploration(self,
                             batch: SampleBatch,
                             **kwargs) -> StateDict:
        """The forward pass for exploration (data collection).

        Args:
            batch: The batch received in the forward pass.

        Returns:
            A dictionary with action logits. The learner will use these
            to create the action distribution.
        """
        return self._forward_inference(batch, **kwargs)

    @override(TorchRLModule)
    def _forward_train(self,
                       batch: SampleBatch,
                       **kwargs) -> StateDict:
        """
        The centralized forward pass for training.

        Args:
            batch: The batch received in the forward pass.

        Returns:
            A dictionary with action logits. The learner will use these
            to create the action distribution.
        """
        obs_tuple = batch[Columns.OBS]["grouped_agents"]
        # Concatenate the tuple of observations into a single tensor for the
        # centralized critic only.
        concat_obs = torch.cat(obs_tuple, dim=-1)

        # The actor remains decentralized during training.  This is the same
        # path used during rollout, so PPO/APPO/SAC actor losses update the
        # executed local policy heads rather than an unused centralized actor.
        action_logits = torch.cat(
            [self._stabilize_action_logits(self.pi_heads[agent_id](obs_tuple[i]))
             for i, agent_id in enumerate(self.agents_id)], dim=-1)

        # The critic alone receives the centralized observation.
        central_embeddings = self.vf_encoder(concat_obs)

        fwd_out = {Columns.ACTION_DIST_INPUTS: action_logits,
                   Columns.EMBEDDINGS: central_embeddings}

        if self.algorithm == RLAlgorithm.SAC.value:
            # FIRST PASS: Compute Q-values for actions sampled from replay buffer to train the critic
            # Concatenate the tuple of actions into a single tensor
            concat_act = torch.cat(batch[Columns.ACTIONS]["grouped_agents"], dim=-1)

            # Embeddings from Q-network encoders with the concatenated observations/actions
            qf_input = torch.cat([concat_obs, concat_act], dim=-1)
            qf_embeddings = self.qf_encoder(qf_input)
            qf_twin_embeddings = self.qf_twin_encoder(qf_input)

            # Q-values from both Q-networks
            fwd_out[QF_PREDS] = self.qf(qf_embeddings).squeeze(-1)
            fwd_out[QF_TWIN_PREDS] = self.qf_twin(qf_twin_embeddings).squeeze(-1)

            # SECOND PASS: Compute Q-values for actions sampled from current policy to train the actor
            # Action distribution from the current policy action_logits
            curr_action_dist = self.action_dist_cls.from_logits(action_logits)
            curr_actions_resampled = curr_action_dist.rsample()

            # Embeddings from Q-network encoders with the current concatenated observations/actions
            curr_qf_input = torch.cat([concat_obs, *curr_actions_resampled["grouped_agents"]], dim=-1)
            curr_qf_embeddings = self.qf_encoder(curr_qf_input)
            curr_qf_twin_embeddings = self.qf_twin_encoder(curr_qf_input)

            # Get Q-values for current policy actions (take minimum of twin Q-networks)
            fwd_out["q_curr"] = torch.min(self.qf(curr_qf_embeddings).squeeze(-1),
                                          self.qf_twin(curr_qf_twin_embeddings).squeeze(-1))
            fwd_out["logp_resampled"] = curr_action_dist.logp(curr_actions_resampled)

            # THIRD PASS: Compute Q-values for actions sampled from target policy to train the critic
            # Concatenate the tuple of next observations into a single tensor
            concat_next_obs = torch.cat(batch[Columns.NEXT_OBS]["grouped_agents"], dim=-1)

            # Get embeddings and action_logits from next observations
            next_obs_tuple = batch[Columns.NEXT_OBS]["grouped_agents"]
            next_obs_action_logits = torch.cat(
                [self._stabilize_action_logits(self.target_pi_heads[agent_id](next_obs_tuple[i]))
                 for i, agent_id in enumerate(self.agents_id)], dim=-1)

            # Target action distribution from the next observation's policy action_logits
            target_action_dist = self.action_dist_cls.from_logits(next_obs_action_logits)
            target_actions_resampled = target_action_dist.sample()

            # Embeddings from target Q-network encoders with the concatenated next observations/actions
            target_qf_input = torch.cat([concat_next_obs, *target_actions_resampled["grouped_agents"]], dim=-1)
            target_qf_embeddings = self.target_qf_encoder(target_qf_input)
            target_qf_twin_embeddings = self.target_qf_twin_encoder(target_qf_input)

            # Get Q-values from target Q-networks
            fwd_out["q_target_next"] = torch.min(self.target_qf(target_qf_embeddings).squeeze(-1),
                                                 self.target_qf_twin(target_qf_twin_embeddings).squeeze(-1))
            fwd_out["logp_next_resampled"] = target_action_dist.logp(target_actions_resampled)

        return fwd_out

    @override(ValueFunctionAPI)
    def compute_values(self,
                       batch: SampleBatch,
                       embeddings: Optional[Any] = None) -> TensorType:
        """
        Computes the value function predictions for the critic.

        Args:
            batch: The batch received in the forward pass.
            embeddings: The embeddings received in the forward pass.

        Returns:
            A tensor with the value function predictions.
        """
        if embeddings is None:
            # Concatenate the tuple of observations into a single tensor
            concat_obs = torch.cat(batch[Columns.OBS]["grouped_agents"], dim=-1)

            # Get embeddings from the centralized value encoder.
            embeddings = self.vf_encoder(concat_obs)

        # Get value output from the value head
        vf_preds = self.vf_head(embeddings).squeeze(-1)

        return vf_preds

    @override(TargetNetworkAPI)
    def make_target_networks(self) -> None:
        """Creates the required target networks for this RLModule."""
        # SAC needs target copies of the decentralized actor heads.  PPO/APPO
        # simply ignore these copies, but keeping them here gives all modes a
        # uniform TargetNetworkAPI implementation.
        self.target_pi_heads = torch.nn.ModuleDict({agent_id: make_target_network(self.pi_heads[agent_id]) for agent_id in self.agents_id})

        if self.algorithm == RLAlgorithm.SAC.value:
            self.target_qf_encoder = make_target_network(self.qf_encoder)
            self.target_qf = make_target_network(self.qf)
            self.target_qf_twin_encoder = make_target_network(self.qf_twin_encoder)
            self.target_qf_twin = make_target_network(self.qf_twin)

    @override(TargetNetworkAPI)
    def get_target_network_pairs(self) -> List[Tuple[NetworkType, NetworkType]]:
        """Returns a list of (main_net, target_net) tuples for the target networks."""
        target_pairs = [(self.pi_heads[agent_id], self.target_pi_heads[agent_id])
                        for agent_id in self.agents_id]

        if self.algorithm == RLAlgorithm.SAC.value:
            target_pairs.extend([(self.qf_encoder, self.target_qf_encoder),
                                 (self.qf, self.target_qf),
                                 (self.qf_twin_encoder, self.target_qf_twin_encoder),
                                 (self.qf_twin, self.target_qf_twin)])

        return target_pairs

    @override(TargetNetworkAPI)
    def forward_target(self, batch: StateDict) -> StateDict:
        """
        Performs the forward pass through the target networks.

        Args:
            batch: The batch received in the forward pass.

        Returns:
            A dictionary with action logits. The learner will use these
            to create the action distribution.
        """
        obs_tuple = batch[Columns.OBS]["grouped_agents"]
        target_action_logits = torch.cat(
            [self._stabilize_action_logits(self.target_pi_heads[agent_id](obs_tuple[i]))
             for i, agent_id in enumerate(self.agents_id)], dim=-1)
        return {TARGET_NETWORK_ACTION_DIST_INPUTS: target_action_logits}

    @override(QNetAPI)
    def compute_q_values(self, batch: StateDict) -> StateDict:
        """
        Computes Q-values for SAC.

        Args:
            batch: The batch received in the forward pass.

        Returns:
            A dictionary containing the Q-value predictions.
        """
        # Concatenate the tuple of observations into a single tensor
        concat_obs = torch.cat(batch[Columns.OBS]["grouped_agents"], dim=-1)
        concat_act = torch.cat(batch[Columns.ACTIONS]["grouped_agents"], dim=-1)

        # Concatenate observations and actions for Q-network input
        qf_input = torch.cat([concat_obs, concat_act], dim=-1)

        # Get embeddings from Q-network encoders
        qf_embeddings = self.qf_encoder(qf_input)
        qf_twin_embeddings = self.qf_twin_encoder(qf_input)

        # Get Q-values from both Q-network heads
        return {QF_PREDS: self.qf(qf_embeddings).squeeze(-1),
                QF_TWIN_PREDS: self.qf_twin(qf_twin_embeddings).squeeze(-1)}

    @override(QNetAPI)
    def compute_advantage_distribution(self, batch: StateDict) -> StateDict:
        """
        Computes the advantage distribution for SAC.

        Note: This method is required by QNetAPI but for non-distributional
        Q-learning (standard SAC), it's a simpler implementation.

        Args:
            batch: The batch containing forward pass outputs.

        Returns:
            A dictionary with Q-values.
        """
        q_values = self.compute_q_values(batch)

        return {QF_PREDS: q_values[QF_PREDS],
                QF_TWIN_PREDS: q_values[QF_TWIN_PREDS]}

    @staticmethod
    def _get_encoder_network(input_dim: int,
                             embedding_dim: int = 64,
                             bias: bool = True) -> NetworkType:
        """Creates a shared encoder network for the policy and Q-networks.

        Args:
            input_dim: The dimension of the input.
            embedding_dim: The dimension of the embedding.
            bias: Whether to use bias in the linear layers.

        Returns:
            A shared encoder network for the policy and Q-networks.
        """
        return torch.nn.Sequential(torch.nn.Linear(input_dim, embedding_dim, bias=bias),
                                   torch.nn.ReLU(),
                                   torch.nn.Linear(embedding_dim, embedding_dim, bias=bias),
                                   torch.nn.ReLU())

    @staticmethod
    def _get_head_network(embedding_dim: int,
                          output_dim: int,
                          bias: bool = True) -> NetworkType:
        """Creates a head network for the policy and Q-networks.

        Args:
            embedding_dim: The dimension of the embedding.
            output_dim: The dimension of the output.
            bias: Whether to use bias in the linear layer.

        Returns:
            A head network for the policy and Q-networks.
        """
        return torch.nn.Linear(embedding_dim, output_dim, bias=bias)

    @staticmethod
    def _get_network(input_dim: int,
                     output_dim: int,
                     embedding_dim: int = 64,
                     bias: bool = True) -> torch.nn.Sequential:
        """Creates a network for an agent's decentralized head.

        Args:
            input_dim: The dimension of the input.
            output_dim: The dimension of the output.
            embedding_dim: The dimension of the embedding.
            bias: Whether to use bias in the linear layer.

        Returns:
            A network for an agent's decentralized head.
        """
        return torch.nn.Sequential(torch.nn.Linear(input_dim, embedding_dim, bias=bias),
                                   torch.nn.ReLU(),
                                   torch.nn.Linear(embedding_dim, embedding_dim, bias=bias),
                                   torch.nn.ReLU(),
                                   torch.nn.Linear(embedding_dim, output_dim, bias=bias))

    def _get_distribution_class(self) -> TorchMultiDistribution:
        """Creates a TorchMultiDistribution class with a baked-in dict structure.

        Returns:
            A TorchMultiDistribution class with a baked-in dict structure.
        """
        tuple_space = self.action_space["grouped_agents"]
        child_dist_cls = TorchSquashedGaussian if self.algorithm == RLAlgorithm.SAC.value else TorchDiagGaussian

        class CustomTorchMultiDistribution(TorchMultiDistribution):
            @classmethod
            def from_logits(cls, logits, **kwargs):
                return super().from_logits(logits=logits,
                                           child_distribution_cls_struct={"grouped_agents": tuple([child_dist_cls] * len(tuple_space.spaces))},
                                           input_lens={"grouped_agents": tuple([child_dist_cls.required_input_dim(s) for s in tuple_space.spaces])},
                                           **kwargs)

        return CustomTorchMultiDistribution

    def _stabilize_action_logits(self, action_logits: TensorType) -> TensorType:
        """Bound one agent's Gaussian log-scales, leaving means unchanged."""
        means, log_stds = action_logits.chunk(2, dim=-1)
        return torch.cat((means, log_stds.clamp(_LOG_STD_MIN, _LOG_STD_MAX)), dim=-1)
