"""Paper-aligned MARLEM Case 6 scenario construction.

The empirical paper gives the eight participant capacities, batteries and
IEEE-34 node identifiers, but does not publish a mapping from its profile
names to the bundled CSV columns. We therefore use deterministic generation
columns and distinct demand columns, and record the mapping in the config.
"""

from pathlib import Path
from typing import Any, Dict, List

from .agent.battery import Battery
from .agent.der import DERAgent
from .grid.base import GridTopology
from .grid.network import GridNetwork
from .market.dso import DSOAgent
from .market.matching import MarketConfig
from .market.mechanism import ClearingMechanism
from .profile.der import DERProfileHandler
from .profile.dso import DSOProfileHandler


# Scenario constants and paper mappings.
CASE6_PARTICIPANTS = (
    ("small_industry", 180.0, 108.0, "840"),
    ("hospital", 170.0, 85.0, "890"),
    ("university", 140.0, 98.0, "844"),
    ("mall", 130.0, 78.0, "816"),
    ("residential", 80.0, 64.0, "800"),
    ("apartment", 75.0, 52.5, "830"),
    ("solar", 180.0, 180.0, "848"),
    ("parking", 160.0, 144.0, "860"),
)
CASE6_DEMAND_COLUMNS = (
    "profile_1",
    "profile_2",
    "profile_3",
    "profile_11",
    "profile_12",
    "profile_13",
    "profile_14",
    "profile_15",
)
CASE6_PAPER_NAMES = {
    "small_industry": "Small Industry",
    "hospital": "Community Hospital",
    "university": "University Campus",
    "mall": "Shopping Mall",
    "residential": "Residential Complex",
    "apartment": "Apartment Building",
    "solar": "Community Solar Farm",
    "parking": "Parking Lot",
}


# Profile paths and participant construction.
def _data_paths() -> Dict[str, Path]:
    root = Path(__file__).resolve().parents[1]
    return {
        "generation": root / "data" / "generation" / "generation_60min.csv",
        "demand": root / "data" / "demand" / "demand_60min.csv",
        "fit": root / "data" / "prices" / "fit_60min.csv",
        "utility": root / "data" / "prices" / "utility_60min.csv",
    }


def build_case6_agents(max_steps: int = 24, seed: int = 42) -> List[DERAgent]:
    """Build the eight paper participants with distinct normalized profiles."""
    paths = _data_paths()
    agents: List[DERAgent] = []
    for index, (name, capacity, battery_capacity, node_id) in enumerate(
        CASE6_PARTICIPANTS
    ):
        generation_column = f"profile_{index + 1}"
        demand_column = CASE6_DEMAND_COLUMNS[index]
        handler = DERProfileHandler(
            min_quantity=0.1,
            max_quantity=180.0,
            generation_file_path=str(paths["generation"]),
            demand_file_path=str(paths["demand"]),
            generation_column=generation_column,
            demand_column=demand_column,
            file_profile_mode="normalized",
            seed=seed + index,
        )
        generation, demand = handler.get_energy_profiles(max_steps, capacity)
        agents.append(
            DERAgent(
                id=name,
                capacity=capacity,
                battery=Battery(
                    nominal_capacity=battery_capacity,
                    min_soc=0.05,
                    max_soc=0.95,
                    charge_efficiency=0.95,
                    discharge_efficiency=0.95,
                ),
                node_id=node_id,
                generation_profile=generation,
                demand_profile=demand,
            )
        )
    return agents


# Training configuration.
def build_case6_config(
    seed: int = 42,
    max_steps: int = 24,
    blockchain_difficulty: int = 0,
) -> Dict[str, Any]:
    """Return the corrected, paper-aligned Case 6 environment config.

    ``blockchain_difficulty=0`` is the recommended training setting.  Set it
    to 2 for a paper/audit run where the original proof-of-work overhead is
    intentionally retained.
    """
    paths = _data_paths()
    grid = GridNetwork(GridTopology.IEEE34, num_nodes=8, capacity=1800.0, seed=seed)
    market = MarketConfig(
        min_price=20.0,
        max_price=600.0,
        min_quantity=0.1,
        max_quantity=180.0,
        price_mechanism=ClearingMechanism.AVERAGE,
        enable_partner_preference=True,
        blockchain_difficulty=blockchain_difficulty,
        visualize_blockchain=False,
    )
    dso_handler = DSOProfileHandler(
        min_price=20.0,
        max_price=600.0,
        feed_in_tariff_file_path=str(paths["fit"]),
        utility_price_file_path=str(paths["utility"]),
        file_profile_mode="normalized",
        seed=seed,
    )
    fit, utility = dso_handler.get_price_profiles(max_steps)
    dso = DSOAgent("dso", fit, utility, grid, node_id="800")
    config: Dict[str, Any] = {
        "scenario_id": "case6-reconstructed-v1",
        "profile_mapping_status": "reconstructed-unverified",
        "max_steps": max_steps,
        "agents": build_case6_agents(max_steps, seed),
        "market_config": market,
        "grid_network": grid,
        "dso": dso,
        "der_profile_handler": DERProfileHandler(
            min_quantity=0.1,
            max_quantity=180.0,
            generation_file_path=str(paths["generation"]),
            demand_file_path=str(paths["demand"]),
            file_profile_mode="normalized",
            seed=seed,
        ),
        "dso_profile_handler": dso_handler,
        "enable_reset_dso_profiles": False,
        "enable_asynchronous_order": True,
        "max_error": 0.30,
        "forecast_error_mode": "bounded_multiplicative_uniform",
        "num_anchor": 4,
        "seed": seed,
        "unit_convention": "energy=kWh, power=kW, price=currency/kWh",
        "profile_column_mapping": {
            name: {
                "generation": f"profile_{index + 1}",
                "demand": CASE6_DEMAND_COLUMNS[index],
            }
            for index, (name, *_rest) in enumerate(CASE6_PARTICIPANTS)
        },
        "paper_node_mapping": {
            name: node for name, _cap, _battery, node in CASE6_PARTICIPANTS
        },
        "paper_participant_names": CASE6_PAPER_NAMES,
        "algorithm_hyperparameters": {
            "ppo": {
                "learning_rate": 1e-5,
                "gamma": 0.99,
                "entropy_coeff": 0.01,
                "grad_clip": 0.5,
                "clip_param": 0.2,
                "minibatch_size": 128,
                "gae": True,
            },
            "appo": {
                "learning_rate": 1e-5,
                "gamma": 0.99,
                "entropy_coeff": 0.01,
                "grad_clip": 0.5,
                "vtrace": True,
            },
            "sac": {
                "actor_learning_rate": 1e-5,
                "critic_learning_rate": 1e-5,
                "gamma": 0.99,
                "entropy": "dynamic",
                "grad_clip": 0.5,
                "buffer_capacity": 1000,
            },
        },
    }
    grid.assign_agents_to_graph(config["agents"])
    return config


# Held-out evaluation configuration and seed scheduling.
def build_case6_evaluation_config(
    seed: int = 10042, max_steps: int = 24
) -> Dict[str, Any]:
    """Build an independently seeded held-out evaluation scenario."""
    config = build_case6_config(seed=seed, max_steps=max_steps, blockchain_difficulty=0)
    config["evaluation_split"] = "held_out"
    config["evaluation_seed_base"] = seed
    return config


def case6_seed_schedule(base_seed: int = 10042, episodes: int = 100) -> List[int]:
    """Return reproducible, distinct evaluation episode seeds."""
    return [base_seed + episode for episode in range(episodes)]
