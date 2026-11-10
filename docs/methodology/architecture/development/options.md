# Adding an option

> Some parts of the framework are choices a scenario or an experiment makes by name: how
> the losses are shared, which reward the agents learn from, which signals they see.
> Each of these follows one pattern, so a new option is a class or a list added in
> one place, and the rest of the framework (the setting's check, the Studio, the
> tests) picks it up.

## The pattern

| Part | What it is | Example: loss allocation |
|---|---|---|
| **Contract** | A base class whose methods every option implements | [`LossAllocation`](../../../../core/grid/losses.py): `shares(net, losses)` |
| **Registry** | A dict from the option's name to its class | `LOSS_ALLOCATIONS = {"bcdla": ..., "pro_rata": ...}` |
| **Builder** | Turns the name into an instance, refusing an unknown name with the list of known ones | `build_loss_allocation(name)` |
| **Setting** | The scenario or `env_config` field that names the option | `dso.losses` |
| **Test** | One test run for every registered option, checking the contract | `test_every_rule_shares_out_exactly_the_measured_losses` |

Adding an option is then: write the class, add it to the registry. Its name becomes a
valid value of the setting, the Studio lists it where it lists the others, and the
test covers it.

## The choices built this way

| Choice | Setting | Registry and contract | Options now | Test for every option |
|---|---|---|---|---|
| Who pays the network's losses | `dso.losses` ([Configuration](../../../using/running/config.md#dso)) | `LOSS_ALLOCATIONS`, `LossAllocation` in [losses.py](../../../../core/grid/losses.py) | `bcdla`, `pro_rata`; and `"trades"`, [P1]'s eq. 18 per trade, which needs no rule | [test_losses.py](../../../../tests/market/test_losses.py) |
| The reward | `env_config.reward` ([Configuration](../../../using/running/config.md#env_config)) | `REWARDS`, `Reward` in [reward.py](../../../../core/env/reward.py) | `bill`, `salazar` | `test_every_reward_pays_every_agent` in [test_market_env.py](../../../../tests/market/test_market_env.py) |
| What the agents see | `env_config.observation` | `OBSERVATIONS` in [market_env.py](../../../../core/env/market_env.py): a tuple of signal names; the signals in [signals.py](../../../../core/market/signals.py) | `paper`, `pruned` | `test_every_observation_set_names_known_signals` |

The reward's and the observation's names are also listed in
[env_defaults.py](../../../../core/env_defaults.py) (`REWARD_NAMES`,
`OBSERVATION_NAMES`): the runner checks an experiment against them without loading
Ray, and a test fails when the two lists differ.

Other choices are a fixed list in the function that uses them, because each option is a
formula of a few lines: the grid method (`grid.method`), the voltage drop
(`dso.voltage_drop`), the graph model's capacity rule (`grid.graph_capacity`) and the
pricing mechanism (`market.mechanism`). Adding one of those means editing that
function; if one of them grows a third or fourth option, it moves to the pattern above.

## Worked example: a loss rule

A rule that charges each element in proportion to its current, wherever it is: the
contract asks only for `shares`.

```python
class ByCurrent(LossAllocation):
    """The network's losses shared by each element's current magnitude."""

    name = "by_current"
    label = "Measured, shared by current"   # how the Studio's Scenario page names it

    def shares(self, net, losses):
        current = {e: abs(i) for e, i in _element_currents(net).items()}
        total, weight = sum(losses.values()), sum(current.values())
        return {e: total * c / weight for e, c in current.items()} if weight else {}


LOSS_ALLOCATIONS = {
    rule.name: rule for rule in (BranchCurrentDecomposition, ProRata, ByCurrent)
}
```

`allocate`, which the market calls, does the rest: it refuses a meshed network when the
rule sets `radial_only`, reads every line's and transformer's measured loss and reports
what the rule left unallocated. From then on `"dso": {"losses": "by_current"}` is a
valid scenario, `DsoSetup.problems` accepts it, the Scenario page offers it, and the
test checks that its shares add up to the measured losses.

The reward works the same way: subclass `Reward`, implement `step` (the step's record
in, one number per agent out), and add the class to `REWARDS` and its name to
`REWARD_NAMES`. An observation set is a tuple of signal names under a new key of
`OBSERVATIONS`; a new signal is a function in `signals.py`, registered in its group's
dict.
