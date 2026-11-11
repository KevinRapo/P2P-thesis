"""Loss allocation (``core/grid/losses.py``): the step's power-flow losses shared out.

Every rule must share out the network's measured losses, less what it leaves with the
DSO: nothing for pro rata, the transformer's no-load (iron) loss for branch current
decomposition, which shares only the current-dependent losses. It is checked by hand
on a small feeder: a branch with one element below gives that element all of its loss,
and a generator whose export runs against a branch's flow gets a credit. Near a
balanced transformer (a household's export covering another's demand) the shares stay
bounded, which they did not while the no-load loss was shared by current.
"""

from __future__ import annotations

import pandapower as pp
import pytest

from core.grid.losses import (
    LOSS_ALLOCATIONS,
    BranchCurrentDecomposition,
    ProRata,
    branch_losses_kw,
    build_loss_allocation,
    independent_loops,
    trafo_copper_losses_kw,
)


def feeder(
    pv_kw: float = 20.0,
    loop: bool = False,
    parallel: bool = False,
    load_kvar: float = 5.0,
):
    """MV external grid -> transformer -> b1 -> line A -> b2 -> line B -> b3, a 30 kW
    load at b3 and PV at b2; solved. ``loop`` closes b3 back to b1, ``parallel``
    doubles line A."""
    net = pp.create_empty_network()
    mv = pp.create_bus(net, 20.0)
    b1, b2, b3 = (pp.create_bus(net, 0.4) for _ in range(3))
    pp.create_ext_grid(net, mv)
    pp.create_transformer(net, mv, b1, "0.25 MVA 20/0.4 kV")
    pp.create_line(net, b1, b2, 0.3, "NAYY 4x150 SE", name="A")
    if parallel:
        pp.create_line(net, b1, b2, 0.3, "NAYY 4x150 SE", name="A2")
    pp.create_line(net, b2, b3, 0.2, "NAYY 4x150 SE", name="B")
    if loop:
        pp.create_line(net, b3, b1, 0.4, "NAYY 4x150 SE", name="loop")
    pp.create_load(net, b3, p_mw=0.030, q_mvar=load_kvar / 1000.0)
    if pv_kw:
        pp.create_sgen(net, b2, p_mw=pv_kw / 1000.0)
    pp.runpp(net)
    return net


def line(net, name: str) -> int:
    return int(net.line.index[net.line.name == name][0])


@pytest.mark.parametrize("name", sorted(LOSS_ALLOCATIONS))
def test_every_rule_shares_out_the_measured_losses_less_what_stays_with_the_dso(name):
    net = feeder()
    found = build_loss_allocation(name).allocate(net)
    measured = 1000.0 * (net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum())

    assert found.method == name and LOSS_ALLOCATIONS[name].label  # the Studio names it
    assert found.total_kw == pytest.approx(measured)
    assert sum(found.by_element.values()) + found.residual_kw == pytest.approx(
        measured, rel=1e-9
    )

    if name == "pro_rata":
        assert found.residual_kw == pytest.approx(0.0, abs=1e-9)


def test_bcdla_leaves_the_transformers_no_load_loss_with_the_dso():
    """The shares add up to the measured loss less the no-load part of the
    transformer's: its measured loss minus its copper loss, here its ``pfe_kw``
    (0.8 kW) within the voltage's effect."""
    net = feeder()
    found = BranchCurrentDecomposition().allocate(net)
    measured = branch_losses_kw(net)[("trafo", 0)]
    copper = trafo_copper_losses_kw(net)[("trafo", 0)]

    assert found.residual_kw == pytest.approx(measured - copper, rel=1e-9)
    assert found.residual_kw == pytest.approx(float(net.trafo.pfe_kw[0]), rel=0.05)
    assert sum(found.by_element.values()) == pytest.approx(
        found.total_kw - found.residual_kw, rel=1e-9
    )


def test_bcdla_shares_stay_bounded_where_the_transformer_current_nearly_vanishes():
    """The PV at b2 covers the load at b3 (30 kW each, no reactive power): the
    transformer carries only the line losses. Sharing its constant no-load loss by
    current gave the PV about -88 kW and the load +89 kW out of a 1 kW loss; now
    every share is below the network's loss."""
    for pv_kw in (29.0, 29.9, 30.0, 30.1):
        found = BranchCurrentDecomposition().allocate(feeder(pv_kw, load_kvar=0.0))

        assert found.residual_kw > 0
        assert all(abs(s) < found.total_kw for s in found.by_element.values()), pv_kw
        assert sum(found.by_element.values()) == pytest.approx(
            found.total_kw - found.residual_kw, rel=1e-9
        )


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError, match="choose from"):
        build_loss_allocation("nobody")


def test_bcdla_gives_a_branch_with_one_element_below_to_that_element():
    """Line B feeds only the load: all of B's loss is the load's."""
    net = feeder()
    losses = branch_losses_kw(net)
    load = ("load", 0)
    only_b = {("line", line(net, "B")): losses[("line", line(net, "B"))]}

    found = BranchCurrentDecomposition().shares(net, only_b)
    assert found == {load: pytest.approx(only_b[("line", line(net, "B"))])}


def test_bcdla_credits_a_generator_that_relieves_a_branch():
    """The PV at b2 covers part of the load below it, so less flows through line A
    and the transformer: its share is negative, and the load's is more than all the
    current-dependent loss of the network."""
    found = BranchCurrentDecomposition().allocate(feeder(pv_kw=20.0))
    pv, load = found.by_element[("sgen", 0)], found.by_element[("load", 0)]

    assert pv < 0 < load
    assert load > found.total_kw - found.residual_kw


def test_bcdla_without_the_generator_gives_the_load_every_current_dependent_loss():
    found = BranchCurrentDecomposition().allocate(feeder(pv_kw=0.0))
    assert found.by_element == {
        ("load", 0): pytest.approx(found.total_kw - found.residual_kw)
    }


def test_bcdla_shares_parallel_lines_and_refuses_a_loop():
    found = BranchCurrentDecomposition().allocate(feeder(parallel=True))
    assert sum(found.by_element.values()) == pytest.approx(
        found.total_kw - found.residual_kw
    )

    meshed = feeder(loop=True)
    assert independent_loops(meshed) == 1
    with pytest.raises(ValueError, match="radial"):
        BranchCurrentDecomposition().allocate(meshed)

    assert ProRata().allocate(meshed).residual_kw == pytest.approx(0.0, abs=1e-9)


def test_pro_rata_shares_by_active_power():
    found = ProRata().allocate(feeder(pv_kw=20.0))
    pv, load = found.by_element[("sgen", 0)], found.by_element[("load", 0)]
    assert load / pv == pytest.approx(30.0 / 20.0, rel=1e-3)


def test_simbench_networks_radial_or_not():
    """The thesis network and an MV network operated with open rings are radial with
    their switches as set; MV rural has one closed loop."""
    import simbench as sb

    for code, loops in (("1-LV-rural3--2-sw", 0), ("1-MV-rural--0-sw", 1)):
        assert independent_loops(sb.get_simbench_net(code)) == loops, code


def test_bcdla_on_the_thesis_network():
    """On 1-LV-rural3--2-sw at its static values: every kW of current-dependent loss
    allocated; what is left is the transformer's no-load loss."""
    import simbench as sb

    net = sb.get_simbench_net("1-LV-rural3--2-sw")
    pp.runpp(net)
    found = BranchCurrentDecomposition().allocate(net)

    assert found.total_kw > 0
    assert 0 < found.residual_kw < found.total_kw
    assert found.residual_kw == pytest.approx(
        float(net.trafo.pfe_kw.sum()), rel=0.1
    )


# --------------------------------------------------------------------------------------
# In the market: ``dso.losses``
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def days():
    """One day of validate_market with eq. 18's losses and one with BCDLA's."""
    from pathlib import Path

    from core.config import store
    from core.market.lem import LocalEnergyMarket

    path = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
    played = {}

    for rule in ("trades", "bcdla"):
        scenario = store.load(path)
        scenario.dso.losses = rule
        market = LocalEnergyMarket(scenario)
        market.reset()
        played[rule] = (market, market.run_to_end())

    return played


def test_with_eq_18_nothing_changes(days):
    _, records = days["trades"]
    assert all(r.grid.loss_shares_kwh == {} for r in records)
    assert all(o.loss_charge == 0.0 for r in records for o in r.participants.values())
    assert any(t.fee_parts.transmission > 0 for r in records for t in r.trades)


def test_each_participant_pays_its_share_at_the_utility_price(days):
    """With BCDLA every participant pays its share of the measured losses at the
    step's utility price, inside its fees; F_trans is 0; the DSO collects it."""
    _, records = days["bcdla"]
    assert any(r.grid.loss_shares_kwh for r in records)
    # Shares can be credits, so the participants' sum may even exceed the network's
    # losses when background elements are credited; the whole network's shares
    # always add up to them (test_every_rule_shares_out_exactly_the_measured_losses).

    for r in records:
        assert all(t.fee_parts.transmission == 0.0 for t in r.trades)
        charges = 0.0

        for pid, o in r.participants.items():
            share = r.grid.loss_shares_kwh.get(pid, 0.0)
            assert o.loss_charge == pytest.approx(share * r.inputs.utility_price)
            trade_fees = sum(
                t.buyer_fee if t.buyer_id == pid else t.seller_fee
                for t in r.trades
                if pid in (t.buyer_id, t.seller_id)
            )
            assert o.fees == pytest.approx(trade_fees + o.loss_charge)
            charges += o.loss_charge

        trade_fees = sum(t.buyer_fee + t.seller_fee for t in r.trades)
        assert r.dso.fees == pytest.approx(trade_fees + charges)


def test_an_unknown_rule_is_a_scenario_problem():
    from core.config.scenario import DsoSetup

    assert any("Losses" in p for p in DsoSetup(losses="nobody").problems(1.0))
    assert not any("Losses" in p for p in DsoSetup(losses="bcdla").problems(1.0))
