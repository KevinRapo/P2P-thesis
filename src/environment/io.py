"""
Environment configuration management utilities.

This module provides functionality to save and load environment configurations
to/from JSON files, ensuring consistency between training and inference.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..agent.battery import Battery
from ..agent.der import DERAgent
from ..grid.base import GridTopology
from ..grid.network import GridNetwork
from ..market.dso import DSOAgent
from ..market.matching import MarketConfig
from ..market.mechanism import ClearingMechanism
from ..profile.der import DERProfileHandler
from ..profile.dso import DSOProfileHandler
from ..root import __main__


class EnvConfigHandler:
    """Manages LEM environment configuration serialization and deserialization."""

    @classmethod
    def save(cls,
             env_config: Dict[str, Any],
             storage_path: str = None,
             name: str = "env_config",
             decimals: Optional[int] = None) -> None:
        """Save environment configuration to JSON file.

        Args:
            env_config: Environment configuration dictionary
            storage_path: Directory path where to save the configuration (default: downloads/)
            name: Name of the configuration file without .json extension (default: env_config)
            decimals: Optional number of decimal places; None preserves profiles exactly.
        """
        # Ensure storage_path is a Path object
        storage_path = Path(__main__) / "downloads" if storage_path is None else Path(storage_path)

        # Create the full file path
        config_path = storage_path / f"{name}.json"

        # Create directory if it doesn"t exist
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a serializable version of env_config
        serializable_config = cls._make_config_serializable(env_config, decimals)

        # Save to JSON file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(serializable_config, f, indent=2)

    @classmethod
    def load(cls, file_path: str) -> Dict[str, Any]:
        """Load environment configuration from JSON file.

        Args:
            file_path: Path to the configuration file

        Returns:
            Environment configuration dictionary
        """
        config_path = Path(file_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Environment configuration not found at: {config_path}")

        # Load from JSON file
        with open(config_path, "r") as f:
            serializable_config = json.load(f)

        # Restore the original configuration with proper objects
        return cls._restore_config_from_serializable(serializable_config)

    @classmethod
    def _make_config_serializable(cls,
                                  config: Dict[str, Any],
                                  decimals: Optional[int] = None) -> Dict[str, Any]:
        """Convert environment configuration to serializable format.

        Args:
            config: Environment configuration dictionary
            decimals: Optional number of decimal places; None preserves profiles exactly.

        Returns:
            Serializable configuration dictionary
        """
        serializable = {}

        for key, value in config.items():
            # Convert MarketConfig to dict
            if key == "market_config":
                market_dict = dict(value.__dict__) if hasattr(value, "__dict__") else value

                # Convert ClearingMechanism enum to its value
                if "price_mechanism" in market_dict and hasattr(market_dict["price_mechanism"], "value"):
                    market_dict["price_mechanism"] = market_dict["price_mechanism"].value

                serializable[key] = market_dict

            # Convert GridNetwork to dict
            elif key == "grid_network":
                if value is not None:
                    serializable[key] = {"topology": value.topology.value if hasattr(value.topology, "value") else str(value.topology),
                                         "num_nodes": value.num_nodes,
                                         "capacity": value.capacity,
                                         "seed": getattr(value, "seed", None)}
                else:
                    serializable[key] = None

            # Convert DSOAgent to dict
            elif key == "dso":
                if value is not None:
                    # Handle grid_network separately to avoid serialization issues
                    grid_network_dict = None
                    if value.grid_network is not None:
                        grid_network_dict = {"topology": value.grid_network.topology.value if hasattr(value.grid_network.topology, "value") else str(value.grid_network.topology),
                                             "num_nodes": value.grid_network.num_nodes,
                                             "capacity": value.grid_network.capacity,
                                             "seed": getattr(value.grid_network, "seed", None)}

                    serializable[key] = {"id": value.id,
                                         "feed_in_tariff": value.feed_in_tariff,
                                         "utility_price": value.utility_price,
                                         "grid_network": grid_network_dict,
                                         "max_buy_quantity": value.max_buy_quantity,
                                         "max_sell_quantity": value.max_sell_quantity,
                                         "node_id": value.node_id}
                else:
                    serializable[key] = None

            # Convert list of DERAgents to dict
            elif key == "agents":
                serializable[key] = []
                for agent in value:
                    agent_dict = {"id": agent.id,
                                  "capacity": agent.capacity,
                                  "battery": {"nominal_capacity": agent.battery.nominal_capacity,
                                              "min_soc": agent.battery.min_soc,
                                              "max_soc": agent.battery.max_soc,
                                              "charge_efficiency": agent.battery.charge_efficiency,
                                              "discharge_efficiency": agent.battery.discharge_efficiency,
                                              "max_charge_power": agent.battery.max_charge_power,
                                              "max_discharge_power": agent.battery.max_discharge_power,
                                              "time_step_hours": agent.battery.time_step_hours,
                                              "initial_soc": agent.battery.initial_soc} if agent.battery else None,
                                              "node_id": agent.node_id,
                                              "generation_profile": [float(val) if decimals is None else round(float(val), decimals) for val in agent.generation_profile],
                                              "demand_profile": [float(val) if decimals is None else round(float(val), decimals) for val in agent.demand_profile]}

                    serializable[key].append(agent_dict)

            # Convert DERProfileHandler or DSOProfileHandler to dict
            elif key in ["der_profile_handler", "dso_profile_handler"]:
                if value is not None:
                    serializable[key] = {"min_quantity": getattr(value, "min_quantity", None),
                                         "max_quantity": getattr(value, "max_quantity", None),
                                         "min_price": getattr(value, "min_price", None),
                                         "max_price": getattr(value, "max_price", None),
                                         "generation_file_path": str(value.generation_file_path) if getattr(value, "generation_file_path", None) else None,
                                         "demand_file_path": str(value.demand_file_path) if getattr(value, "demand_file_path", None) else None,
                                         "generation_column": getattr(value, "generation_column", None),
                                         "demand_column": getattr(value, "demand_column", None),
                                         "generation_timestamp_column": getattr(value, "generation_timestamp_column", None),
                                         "demand_timestamp_column": getattr(value, "demand_timestamp_column", None),
                                         "feed_in_tariff_file_path": str(value.feed_in_tariff_file_path) if getattr(value, "feed_in_tariff_file_path", None) else None,
                                         "utility_price_file_path": str(value.utility_price_file_path) if getattr(value, "utility_price_file_path", None) else None,
                                         "feed_in_tariff_column": getattr(value, "feed_in_tariff_column", None),
                                         "utility_price_column": getattr(value, "utility_price_column", None),
                                         "feed_in_tariff_timestamp_column": getattr(value, "feed_in_tariff_timestamp_column", None),
                                         "utility_price_timestamp_column": getattr(value, "utility_price_timestamp_column", None),
                                         "replay_start": getattr(value, "replay_start", None),
                                         "replay_end": getattr(value, "replay_end", None),
                                         "expected_frequency": getattr(value, "expected_frequency", None),
                                         "decimals": getattr(value, "decimals", 1),
                                         "seed": getattr(value, "seed", None)}
                else:
                    serializable[key] = None

            # Keep primitive types as-is
            else:
                serializable[key] = value

        return serializable

    @classmethod
    def _restore_config_from_serializable(cls, serializable_config: Dict[str, Any]) -> Dict[str, Any]:
        """Restore environment configuration from serializable format.

        Args:
            serializable_config: Serializable configuration dictionary

        Returns:
            Environment configuration dictionary with proper objects
        """
        config = {}
        deferred_dso = None
        deferred_dso_seen = False

        for key, value in serializable_config.items():
            # Restore MarketConfig object
            if key == "market_config":
                market_dict = value.copy()

                # Convert price_mechanism string back to ClearingMechanism enum
                if "price_mechanism" in market_dict and isinstance(market_dict["price_mechanism"], str):
                    market_dict["price_mechanism"] = ClearingMechanism(market_dict["price_mechanism"])

                config[key] = MarketConfig(**market_dict)

            # Restore GridNetwork object
            elif key == "grid_network":
                if value is not None:
                    config[key] = GridNetwork(topology=GridTopology[value["topology"]] if isinstance(value["topology"], str) else value["topology"],
                                              num_nodes=value["num_nodes"],
                                              capacity=value["capacity"],
                                              seed=value["seed"])
                else:
                    config[key] = None

            # Restore DSOAgent object
            elif key == "dso":
                deferred_dso = value
                deferred_dso_seen = True

            # Restore list of DERAgents
            elif key == "agents":
                config[key] = []

                for agent_dict in value:
                    # Restore Battery object
                    battery = None
                    if agent_dict["battery"]:
                        battery = Battery(nominal_capacity=agent_dict["battery"]["nominal_capacity"],
                                          min_soc=agent_dict["battery"]["min_soc"],
                                          max_soc=agent_dict["battery"]["max_soc"],
                                          charge_efficiency=agent_dict["battery"]["charge_efficiency"],
                                          discharge_efficiency=agent_dict["battery"]["discharge_efficiency"],
                                          max_charge_power=agent_dict["battery"].get("max_charge_power"),
                                          max_discharge_power=agent_dict["battery"].get("max_discharge_power"),
                                          time_step_hours=agent_dict["battery"].get("time_step_hours", 1.0),
                                          initial_soc=agent_dict["battery"].get("initial_soc"))

                    agent = DERAgent(id=agent_dict["id"],
                                     capacity=agent_dict["capacity"],
                                     battery=battery,
                                     node_id=agent_dict["node_id"],
                                     generation_profile=agent_dict["generation_profile"],
                                     demand_profile=agent_dict["demand_profile"])

                    config[key].append(agent)

            # Restore DERProfileHandler object
            elif key == "der_profile_handler":
                if value is not None:
                    config[key] = DERProfileHandler(min_quantity=value["min_quantity"],
                                                    max_quantity=value["max_quantity"],
                                                    generation_file_path=value.get("generation_file_path"),
                                                    demand_file_path=value.get("demand_file_path"),
                                                    generation_column=value.get("generation_column"),
                                                    demand_column=value.get("demand_column"),
                                                    decimals=value.get("decimals", 1),
                                                    seed=value["seed"],
                                                    generation_timestamp_column=value.get("generation_timestamp_column"),
                                                    demand_timestamp_column=value.get("demand_timestamp_column"),
                                                    replay_start=value.get("replay_start"),
                                                    replay_end=value.get("replay_end"),
                                                    expected_frequency=value.get("expected_frequency"))
                else:
                    config[key] = None

            # Restore DSOProfileHandler object
            elif key == "dso_profile_handler":
                if value is not None:
                    config[key] = DSOProfileHandler(min_price=value["min_price"],
                                                    max_price=value["max_price"],
                                                    feed_in_tariff_file_path=value.get("feed_in_tariff_file_path"),
                                                    utility_price_file_path=value.get("utility_price_file_path"),
                                                    feed_in_tariff_column=value.get("feed_in_tariff_column"),
                                                    utility_price_column=value.get("utility_price_column"),
                                                    decimals=value.get("decimals", 1),
                                                    seed=value["seed"],
                                                    feed_in_tariff_timestamp_column=value.get("feed_in_tariff_timestamp_column"),
                                                    utility_price_timestamp_column=value.get("utility_price_timestamp_column"),
                                                    replay_start=value.get("replay_start"),
                                                    replay_end=value.get("replay_end"),
                                                    expected_frequency=value.get("expected_frequency"))
                else:
                    config[key] = None

            # Keep primitive types as-is
            else:
                config[key] = value

        if deferred_dso_seen and deferred_dso is None:
            config["dso"] = None
        elif deferred_dso is not None:
            dso_grid = config.get("grid_network")
            nested_grid = deferred_dso.get("grid_network")
            if dso_grid is None and nested_grid is not None:
                dso_grid = GridNetwork(
                    topology=GridTopology[nested_grid["topology"]],
                    num_nodes=nested_grid["num_nodes"],
                    capacity=nested_grid["capacity"],
                    seed=nested_grid.get("seed"),
                )
            config["dso"] = DSOAgent(id=deferred_dso["id"],
                                       feed_in_tariff=deferred_dso["feed_in_tariff"],
                                       utility_price=deferred_dso["utility_price"],
                                       grid_network=dso_grid,
                                       max_buy_quantity=deferred_dso.get("max_buy_quantity"),
                                       max_sell_quantity=deferred_dso.get("max_sell_quantity"),
                                       node_id=deferred_dso.get("node_id"))

        return config
