"""The market runs on the real topology of the chosen SimBench network."""

import json
from pathlib import Path

from src_thesis.marlem.simulation.controllers import get_policy
from src_thesis.platform.kernel.factory.environment import (
    build_env,
    build_env_config,
)
from src_thesis.platform.kernel.models.records import ExperimentFile, RunCell
from src_thesis.platform.kernel.models.resolve import resolve

PRESET = (
    Path(__file__).resolve().parents[1]
    / "src_thesis/platform/kernel/presets/case6-3x3.marlem.json"
)


def engine():
    file = resolve(ExperimentFile.model_validate(json.loads(PRESET.read_text("utf-8"))))
    cell = RunCell(kind="noop", algorithm="-", paradigm="-", seed=1)
    return build_env(build_env_config(file, cell, episode_seed=1)), file


def test_agents_sit_on_the_buses_the_file_names() -> None:
    eng, file = engine()
    eng.reset(1)
    nodes = {a.id: a.location.node_id for a in eng.env._agents.values()}
    assert nodes == {p.id: p.bus for p in file.participants}


def test_trades_have_real_network_distances() -> None:
    eng, _ = engine()
    policy = get_policy("net_position")
    policy.reset(1)
    eng.reset(1)
    trades = []
    for _ in range(eng.n_steps):
        trades += eng.step(policy.act(eng.views())).trades
    p2p = [t for t in trades if "DSO" not in (t["buyer_id"], t["seller_id"])]
    assert p2p and all(t["distance"] >= 0 for t in p2p)
    assert any(t["distance"] >= 1 for t in p2p)  # counted in branches


def test_the_graph_has_one_node_per_bus() -> None:
    eng, _ = engine()
    graph = eng.env.grid_network.graph
    assert len(graph.nodes) == eng.env.grid_network.num_nodes
    assert set(graph.pos) == set(graph.nodes)
