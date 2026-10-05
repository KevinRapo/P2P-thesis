"""Components pinched off from the rest: each is fed small stand-ins, not a world.

No SimBench, no environment, no Ray. Each test builds only what the component's
interface (``core/interfaces.py``, the grid contract, ``adapter.provide``) asks
for, so a failure points at that component.
"""

from types import SimpleNamespace

import pytest

from src_thesis.marlem.grid import placement as placement
from src_thesis.marlem.grid.contract import (
    ElementRecord,
    NetworkRef,
)
from src_thesis.marlem.core.orders import Order
from src_thesis.marlem.dso.dso import DSOAgent
from src_thesis.marlem.market.reputation import ReputationHandler


# ------------------------------------------------------------------ marketplace
def _grid(congestion: float) -> SimpleNamespace:
    """A grid as the DSO sees it (``GridView``): only congestion is asked for."""
    return SimpleNamespace(
        capacity=100.0,
        graph=None,
        edge_flows={},
        edge_capacities={},
        calculate_congestion_level=lambda: congestion,
        get_path_congestion=lambda a, b: congestion,
        transmission_loss=lambda d, q, loss_factor=0.03: 0.0,
    )


def _orders() -> tuple[Order, Order]:
    buy = Order("b1", "buyer", 0.3, 5.0, True, 0.0)
    sell = Order("s1", "seller", 0.2, 5.0, False, 0.0)
    return buy, sell


def test_dso_charges_congestion_only_on_a_congested_grid() -> None:
    calm = DSOAgent(feed_in_tariff=[0.1], utility_price=[0.3], grid_network=_grid(0))
    busy = DSOAgent(feed_in_tariff=[0.1], utility_price=[0.3], grid_network=_grid(0.95))
    assert calm.calculate_fees(*_orders(), trade_price=0.25, quantity=5.0) == 0.0
    assert busy.calculate_fees(*_orders(), trade_price=0.25, quantity=5.0) > 0.0


def test_reputation_ranks_any_participant_shaped_object() -> None:
    agents = [
        SimpleNamespace(id=name, reputation=r) for name, r in (("a", 0.2), ("b", 0.9))
    ]
    assert ReputationHandler().get_agent_ranking(agents) == [("b", 0.9), ("a", 0.2)]


# ------------------------------------------------------------------ placement
def _elements() -> list[ElementRecord]:
    """Four buses: a house with PV, a farm with PV and a battery, a shop (load
    only) and a lone battery.
    """
    return [
        ElementRecord("house 2", "load", "2", "H0-A", 4.0),
        ElementRecord("pv 2", "sgen", "2", "PV3", 6.0),
        ElementRecord("farm 3", "load", "3", "L1-A", 9.0),
        ElementRecord("pv 3", "sgen", "3", "PV5", 20.0),
        ElementRecord("battery 3", "storage", "3", "", 5.0),
        ElementRecord("shop 4", "load", "4", "G4-A", 7.0),
        ElementRecord("battery 5", "storage", "5", "", 8.0),
    ]


def test_only_buses_with_flexibility_can_be_participants() -> None:
    elements = _elements()
    assert placement.candidates(elements) == ["2", "3", "5"]  # not the shop's bus 4
    agents = placement.place(elements)
    assert [a["bus"] for a in agents] == ["2", "3", "5"]
    assert [a["role"] for a in agents] == ["generator", "generator_storage", "storage"]
    assert [a["owns"] for a in agents] == [
        {"loads": ["house 2"], "sgens": ["pv 2"]},
        {"loads": ["farm 3"], "sgens": ["pv 3"], "storage": ["battery 3"]},
        {"loads": [], "sgens": [], "storage": ["battery 5"]},
    ]
    assert placement.place([e for e in elements if e.element_type == "load"]) == []


# ------------------------------------------------------------------ grid adapter
@pytest.fixture()
def tiny():
    """A three-bus pandapower net registered under a reference (no SimBench)."""
    pp = pytest.importorskip("pandapower")
    from src_thesis.marlem.grid import simbench as adapter

    net = pp.create_empty_network()
    b0, b1, b2 = (pp.create_bus(net, vn_kv=0.4, name=f"bus {i}") for i in range(3))
    pp.create_ext_grid(net, b0)
    for a, b in ((b0, b1), (b1, b2)):
        pp.create_line(net, a, b, 0.1, "NAYY 4x50 SE", name=f"line {a}-{b}")
    pp.create_load(net, b1, p_mw=0.004, name="load 1")
    pp.create_load(net, b2, p_mw=0.006, name="load 2")
    pp.create_sgen(net, b2, p_mw=0.005, name="pv 2")
    ref = NetworkRef("pandapower_file", "tiny-test-net")
    adapter.provide(ref, net)
    yield adapter, ref
    adapter.provide(ref, None)


def test_adapter_works_on_a_provided_network(tiny) -> None:
    adapter, ref = tiny
    summary = adapter.summary(ref)
    assert (summary.info.buses, summary.info.loads, summary.info.sgens) == (3, 2, 1)
    assert summary.total_load_kw == 10.0 and summary.total_generation_kw == 5.0
    assert [e.id for e in adapter.elements(ref, bus="bus 2")] == ["load 2", "pv 2"]
    assert adapter.topology_view(ref).external_grid_bus == "bus 0"
