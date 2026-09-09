"""End-to-end physical invariants for the restored paper-intended market."""
from copy import deepcopy

import numpy as np
import pytest

from src.agent.battery import Battery
from src.agent.der import DERAgent
from src.environment.lem import LocalEnergyMarket
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


def scenario(steps=4, dt=1., capacity=20., batteries=False):
    grid = GridNetwork(GridTopology.LINE, 2, capacity, seed=1)
    # Fixed distance keeps the 3% line loss hand-computable.
    grid.graph['0']['1']['weight'] = 1.
    grid.edge_capacities[('0', '1')] = capacity
    agents = [DERAgent('seller', 20., node_id='0', generation_profile=[2.]*steps, demand_profile=[0.]*steps),
              DERAgent('buyer', 20., node_id='1', generation_profile=[0.]*steps, demand_profile=[2.]*steps)]
    if batteries:
        agents[0].battery = Battery(10., initial_soc=.5, max_charge_power=1., max_discharge_power=1.)
        agents[1].battery = Battery(10., initial_soc=.5, max_charge_power=1., max_discharge_power=1.)
    dso = DSOAgent('DSO', [.1]*steps, [.6]*steps, grid, max_buy_quantity=0., max_sell_quantity=0.)
    return dict(max_steps=steps, agents=agents, grid_network=grid, dso=dso, seed=7,
                market_config=MarketConfig(min_price=0., max_price=1., min_quantity=0., max_quantity=20.),
                time_step_hours=dt, enable_asynchronous_order=False)


def actions():
    return {'seller': np.array([.2, 2., 0., 3.], dtype=np.float32),
            'buyer': np.array([.5, 2., 1., 3.], dtype=np.float32)}


def test_consecutive_periods_reset_flows_and_preserve_energy_cash():
    env = LocalEnergyMarket(scenario(capacity=5.))
    env.reset(seed=7)
    for step in range(4):
        obs, reward, terminated, truncated, infos = env.step(actions())
        result = env.market.matching_history.history[-1]
        assert result.p2p_volume == pytest.approx(2.)
        assert list(env.grid_network.edge_flows.values()) == pytest.approx([2.])
        assert sum(env.market.cash_ledger.values()) == pytest.approx(0., abs=1e-10)
        assert result.submitted_orders[0].quantity == 2.
        for record in result.physical_settlements.values():
            assert record.balance_error == pytest.approx(0., abs=1e-9)
            assert record.storage_error == pytest.approx(0., abs=1e-9)
        assert all(np.isfinite(list(reward.values())))
        assert terminated['__all__'] is (step==3)
        assert not any(truncated.values())
        assert all(env.observation_spaces[id].contains(value) for id,value in obs.items())
    with pytest.raises(RuntimeError, match='Episode is complete'):
        env.step(actions())


def test_reverse_congestion_and_partial_fill():
    grid = GridNetwork(GridTopology.LINE, 2, 5., seed=1)
    assert grid.update_flow_from_trade('0', '1', 2.)
    assert list(grid.edge_flows.values()) == pytest.approx([-2.])
    assert grid.calculate_congestion_level() == pytest.approx(.4)
    assert grid.max_transfer('0', '1', 10.) == pytest.approx(3.)
    grid.begin_period()
    assert grid.update_flow_from_trade('1', '0', 2.)
    assert list(grid.edge_flows.values()) == pytest.approx([2.])
    assert grid.calculate_congestion_level() == pytest.approx(.4)
    assert grid.max_transfer('1', '0', 10.) == pytest.approx(3.)
    env = LocalEnergyMarket(scenario(1, capacity=1.))
    env.reset()
    env.step(actions())
    assert env.market.matching_history.history[-1].p2p_volume == pytest.approx(1.)


def test_multiedge_losses_and_downstream_capacity_use_same_source_quantity():
    grid = GridNetwork(GridTopology.LINE, 3, 5., seed=1)
    grid.graph['0']['1']['weight'] = 1.
    grid.graph['1']['2']['weight'] = 1.
    grid.edge_capacities[('0', '1')] = 5.
    grid.edge_capacities[('1', '2')] = 2.
    quantity = grid.max_transfer(buyer_node='2', seller_node='0', requested=10.)
    assert quantity == pytest.approx(2. / .97)
    assert grid.path_delivery_factor(buyer_node='2', seller_node='0') == pytest.approx(.97 ** 2)
    assert grid.update_flow_from_trade(buyer_node='2', seller_node='0', quantity=quantity)
    assert grid.edge_flows[('1', '2')] == pytest.approx(2.)


def test_zero_generation_capacity_consumer_can_import():
    config = scenario(1)
    config['agents'][1].capacity = 0.
    env = LocalEnergyMarket(config)
    env.reset()
    env.step(actions())
    settlement = env.market.matching_history.history[-1].physical_settlements['buyer']
    # The line's one-unit distance loses 3% of the seller's 2 kWh.
    assert settlement.imported == pytest.approx(1.94)
    assert settlement.served_demand == pytest.approx(1.94)
    assert settlement.unserved_demand == pytest.approx(.06)


def test_saved_config_preserves_episode_and_custom_grid(tmp_path):
    from src.environment.io import EnvConfigHandler
    config = scenario(2, dt=.5, batteries=True)
    config['grid_network'].graph['0']['1']['weight'] = 2.5
    config['grid_network'].edge_capacities[('0', '1')] = 3.75
    EnvConfigHandler.save(config, str(tmp_path), 'scenario')
    restored = EnvConfigHandler.load(str(tmp_path / 'scenario.json'))
    original_env, restored_env = LocalEnergyMarket(config), LocalEnergyMarket(restored)
    original_env.reset(seed=11)
    restored_env.reset(seed=11)
    for _ in range(2):
        original_env.step(actions())
        restored_env.step(actions())
        assert original_env.info['physical_settlements'] == restored_env.info['physical_settlements']
        assert original_env.info['cash_ledger'] == restored_env.info['cash_ledger']
        assert original_env.info['kpis'] == restored_env.info['kpis']


def test_public_cooperation_observation_matches_completed_settlement():
    env = LocalEnergyMarket(scenario(2, batteries=True))
    env.reset(seed=11)
    obs, _, _, _, _ = env.step(actions())
    keys = ['social_welfare', 'market_liquidity', 'avg_bid_ask_spread',
            'price_volatility', 'supply_demand_imbalance', 'grid_congestion',
            'coordination_score', 'coordination_convergence',
            'der_self_consumption', 'flexibility_utilization']
    for observation in obs.values():
        np.testing.assert_allclose(observation[32:42], [env.info['kpis'][k] for k in keys], atol=1e-6)


def test_cooperation_signals_change_reward_for_same_individual_outcome():
    env = LocalEnergyMarket(scenario(2, batteries=True))
    env.reset(seed=11)
    env.step(actions())
    matching = env.market.matching_history.history[-1]
    order = next(order for order in matching.submitted_orders if order.agent_id == 'buyer')
    low, high = dict(matching.kpis), dict(matching.kpis)
    for key in ('coordination_score', 'coordination_convergence', 'der_self_consumption', 'flexibility_utilization'):
        low[key], high[key] = 0., 1.
    score = lambda kpis: env.reward_handler.calculate_reward(
        env._agents['buyer'], order, matching, kpis, 0., 1.)
    assert score(high) > score(low)


def test_mutual_partner_preference_changes_allocation_priority():
    grid = GridNetwork(GridTopology.LINE, 3, 20., seed=1)
    agents = [DERAgent('cheap', 2., generation_profile=[2.], demand_profile=[0.]),
              DERAgent('preferred', 2., generation_profile=[2.], demand_profile=[0.]),
              DERAgent('buyer', 0., generation_profile=[0.], demand_profile=[2.])]
    control = {'cheap': np.array([.1, 2., 0., 4.], dtype=np.float32),
               'preferred': np.array([.3, 2., 0., 2.], dtype=np.float32),
               'buyer': np.array([.5, 2., 1., 1.], dtype=np.float32)}
    for enabled, expected_first_seller in [(False, 'cheap'), (True, 'preferred')]:
        config = dict(max_steps=1, agents=agents, grid_network=grid, seed=7,
                      dso=DSOAgent('DSO', [.1], [.8], grid, max_buy_quantity=0., max_sell_quantity=0.),
                      market_config=MarketConfig(min_price=0., max_price=1., min_quantity=0.,
                                                 max_quantity=5., enable_partner_preference=enabled))
        env = LocalEnergyMarket(config)
        env.reset(seed=7)
        env.step(control)
        assert env.market.matching_history.history[-1].trades[0].seller_id == expected_first_seller


def test_no_preference_has_a_selectable_continuous_interval():
    env = LocalEnergyMarket(scenario(1))
    control = np.array([.5, 1., 1., len(env.agent_order) + 1.5], dtype=np.float32)
    assert env.action_spaces['buyer'].contains(control)
    assert env.action_handler.get_partner_id(control[-1]) is None


def test_case3_controller_activates_and_records_once_per_period():
    config = scenario(2)
    config['agents'][1].demand_profile = [10., 10.]
    config['dso'].intervention_threshold = .1
    config['dso'].intervention_frequency = 1.
    config['dso'].price_adjustment_factor = .2
    env = LocalEnergyMarket(config)
    env.reset(seed=7)
    for step in range(2):
        env.step(actions())
        assert env.info['dso_intervention']['active']
        assert len(env.dso.intervention_history) == step + 1
        assert env.dso.get_utility_price(step) > config['dso'].utility_price[step]


def test_battery_dispatch_serves_demand_and_uses_environment_timestep():
    env = LocalEnergyMarket(scenario(1, dt=.25, batteries=True))
    env.reset()
    no_trade = {id:np.array([.4,0.,0.,3.],dtype=np.float32) for id in env.agent_order}
    env.step(no_trade)
    buyer = env._agents['buyer']
    assert buyer.battery.cumulative_discharge == pytest.approx(.25)
    assert buyer.cumulative_demand_satisfied == pytest.approx(.25)
    assert buyer.cumulative_demand_deferred == pytest.approx(1.75)
    assert env._agents['seller'].settlements[-1].battery_charge == pytest.approx(.25)


def test_battery_can_export_stored_energy_and_import_for_charging():
    cfg = scenario(1, batteries=True)
    for agent in cfg['agents']:
        agent.generation_profile = [0.]
        agent.demand_profile = [0.]
    env = LocalEnergyMarket(cfg); env.reset()
    env.step(actions())
    assert env._agents['seller'].settlements[-1].battery_discharge == pytest.approx(1.)
    assert env._agents['buyer'].settlements[-1].battery_charge == pytest.approx(.97)


def test_config_reuse_does_not_mutate_or_convert_profiles_twice():
    cfg = scenario(1, dt=.25)
    cfg['profile_values_are_power'] = True
    a,b = LocalEnergyMarket(cfg),LocalEnergyMarket(cfg)
    assert cfg['agents'][0].generation_profile == [2.]
    assert a._agents['seller'].generation_profile == b._agents['seller'].generation_profile == [.5]
    a.reset(); a.step(actions())
    assert b._agents['seller'].settlements == []


def test_generated_tariff_reset_is_reproducible():
    cfg = scenario(24); cfg['enable_reset_dso_profiles']=True
    env = LocalEnergyMarket(cfg)
    env.reset(seed=7); first = deepcopy(env.dso.utility_price)
    env.reset(seed=7)
    assert first == env.dso.utility_price


def test_all_orders_and_raw_controls_remain_unmodified():
    env = LocalEnergyMarket(scenario(1))
    env.reset(); requested=actions(); original=deepcopy(requested)
    env.step(requested)
    for id in requested:
        np.testing.assert_array_equal(requested[id],original[id])


def test_dso_loss_uses_same_route_as_grid_flow():
    cfg = scenario(1); cfg['dso'].max_sell_quantity=20.
    env = LocalEnergyMarket(cfg); env.reset()
    value=actions(); value['seller'][1]=0.
    env.step(value)
    trade=env.market.trades[0]
    assert trade.seller_id=='DSO'
    assert trade.delivered_quantity == pytest.approx(2.)
    assert trade.quantity == pytest.approx(2./.97)
    assert trade.transmission_loss == pytest.approx(trade.quantity*.03)
    assert env._agents['buyer'].cumulative_demand_satisfied == pytest.approx(2.)
