# 02. SimBench grid

> Network sources, loading, assigning profiles to MARLEM agents, the grid contract, and what changes in MARLEM's step.
> Master: [README.md](README.md) · Decisions: D-01 to D-07, D-11, D-12.
> Items marked *(verify)* are to be confirmed against the installed `simbench` 1.6.2 / `pandapower` 3.5.4 in phase P3.

## 1. One grid technology, several network sources (D-02)

The tool has **one** grid implementation: a pandapower adapter running an AC power flow. The paper's abstract NetworkX grid lives only in the separately published validated release (P2). It is not maintained in the tool.

| Source (`grid.source.type`) | Examples | Profiles included? | Notes |
|---|---|---|---|
| `simbench` (primary) | `1-LV-semiurb4--0-sw`, `1-MV-rural--1-sw` | **Yes**: one year at 15 min for every load, generator and storage | The main research world |
| `pandapower_builtin` | `case33bw` (IEEE 33-bus Baran & Wu), `cigre_mv`, `cigre_lv`, `kerber_*`, `mv_oberrhein` | No: profiles are assigned from the SimBench profile catalogue or CSV (§3.3) | Standard feeders at zero cost. `case33bw` has no line ratings, so either add them (§2) or check voltage only. Checked 2026-09-23: all converge. |
| `pandapower_file` | Any pandapower JSON, e.g. a one-time balanced IEEE 34 build | No (as above) | How extra networks enter without code |

Unbalanced networks (IEEE European LV, which needs `runpp_3ph`) are out of scope for the first version.

## 2. Network loading

| Function | Behaviour |
|---|---|
| **Catalog** | List the available networks with metadata: source, voltage level, number of buses, loads, sgens and storage; total load/PV; whether geodata, profiles and line ratings are present. This powers the Studio's Grid page and `marlem grid list`. |
| **Load** | `simbench.get_simbench_net(code)`, `pandapower.networks.<name>()` or `pandapower.from_json(path)`, cached **once per process** as an immutable source |
| **Working copy** | Each environment (and each RLlib env runner) gets its own deep copy; it is reset per episode. The net is never shared or serialised. |
| **Profiles** | SimBench: `simbench.get_absolute_values(net, profiles_instead_of_study_cases=True)` *(verify)*, cached per process |
| **Line ratings** | Taken from the network. If missing: a rule from the experiment file (e.g. a margin over base-case peak current) or a ratings file. If none is set, loading checks are switched off and reported as such. |
| **Summary / topology view** | Plain data for UI and plots: buses with coordinates, lines, transformers, elements per bus. No pandapower objects cross the adapter boundary. |
| **Validation** | Profile tables agree in length and time. Selected bus and element IDs exist. The unmodified net converges at the selected timestep. |

## 3. Profile assignment (the core flexibility)

An **agent** in MARLEM is one market participant with generation, demand and an optional battery. Each agent is tied to the network through a **participant mapping**. The mapping is part of the experiment file (03) and is persisted as data, never as a live net.

### 3.1 Placement: which bus does the agent sit on?

| Mode | Description | Use |
|---|---|---|
| `manual` | The user picks a bus per agent (table or map in the Studio) | Hand-designed studies |
| `by_elements` | The agent adopts the bus of the load or sgen it owns | Default |
| `rule` | Seeded selection by rule, e.g. "N buses with a household load and PV", "feeder ends only", or "spread across feeders" | Scalability (Case 7), sensitivity studies |
| `file` | Import a mapping CSV/JSON | Sharing, reproducing a published mapping |

A rule is resolved into explicit placements when the experiment is validated. The resolved list is stored in the run manifest.

### 3.2 Ownership: which network elements does the agent replace?

The agent **owns** zero or more existing loads, sgens and storage at its bus. Owned elements are driven by the agent's settlement. Unowned elements stay as background (§3.5). If an agent has generation but owns no sgen, the adapter creates one deterministic controllable sgen at its bus.

Validation rejects:
- an element owned twice;
- an owned element on a different bus from the agent;
- unknown IDs;
- agents without a mapping.

### 3.3 Profile source per agent

| Source | Generation / demand come from | Use |
|---|---|---|
| `native` | The owned elements' own SimBench profiles (sum of owned loads; sum of owned sgens) | Default on SimBench; fully consistent network and data |
| `catalog` | Any SimBench profile type (e.g. `H0-B` demand + `PV3` generation), independent of the network | Heterogeneous roles (Cases 2 and 6); **all** non-SimBench networks |
| `csv` | The existing MARLEM data (`data/demand`, `data/generation`) or a user CSV, with an explicit column → agent mapping | Original data; own datasets |
| `synthetic` | MARLEM's procedural generator | Quick tests |

### 3.4 Scaling, time window, resolution

| Option | Choices |
|---|---|
| **Scaling** | Keep absolute values · scale to a peak kW · scale to an annual/daily energy (kWh). Agent `capacity` is derived from the scaled peak. |
| **Time window** | A fixed date (paper-style single day) · a date range · a day **sampler** (day type, season, or random days) with a disjoint held-out set for evaluation |
| **Resolution** | Native 15 min (96 steps per day, `time_step_hours = 0.25`) · hourly aggregation (24 steps, energy-consistent mean of 4 rows). The rule used is recorded in the manifest. |
| **Batteries** | A MARLEM `Battery` spec per agent (capacity, SoC limits, efficiencies, power limit) · or sized from an owned SimBench storage element |
| **Reactive power** | Consumption keeps the load profile's q/p ratio. Generation and battery run at unity power factor. There is a fallback power factor when p = 0. |
| **DSO tariffs** | SimBench has no prices *(verify)*, so tariffs come from the MARLEM tariff CSVs or the synthetic DSO profile handler, aligned to the same time window |

The **day sampler** is what makes "many more profiles" useful: training episodes draw different days, and evaluation uses held-out days. This directly addresses the single-seed, single-day evaluation of the original results (issues I-72 and I-03).

### 3.5 Background elements

| Mode | Behaviour | Use |
|---|---|---|
| `mapped_replacement` (default) | All non-owned elements run with their profiles at the current timestep. Non-SimBench networks use their static values or assigned catalogue profiles. | Realistic feeder |
| `scaled_background` | As above, times a factor | Stress tests (Case 4 congestion) |
| `no_background` | Non-owned elements are set to 0 | Small deterministic tests |

## 4. Time alignment with MARLEM

MARLEM's episode is `max_steps` periods of `time_step_hours`, with quantities in kWh per period. The adapter maps episode step `t` to a profile row range:

```text
row_start = day_start_row + t * rows_per_step      rows_per_step = 1 (15 min) or 4 (hourly)
background p at step t = mean of the p values over the rows in that range
```

- Paper-parity presets use the hourly rule (24 steps) (D-07).
- A 15-minute experiment is a different experiment file, not a silent resampling.

## 5. Grid contract (the seam)

The existing stub [contract_new.py](../../../src_thesis/marketplace/grid/contract_new.py) is extended to:

```python
@dataclass(frozen=True)
class ParticipantInjection:          # built from settlement, never from trades
    participant_id: str
    bus_id: str
    production_kw: float             # (generation − curtailment + battery_discharge) / h
    consumption_kw: float            # (served_demand + battery_charge) / h
    net_injection_kw: float          # production − consumption  (= (exports − imports) / h)

@dataclass(frozen=True)
class GridViolation:
    code: str                        # "V_LOW", "V_HIGH", "LINE_OVERLOAD", "TRAFO_OVERLOAD", "NOT_CONVERGED"
    element_type: str
    element_id: str | None
    observed: float | None
    limit: float | None

@dataclass(frozen=True)
class GridAssessment:
    step: int
    converged: bool
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_percent: float | None      # None if the network has no ratings
    max_trafo_loading_percent: float | None
    losses_kwh: float | None
    external_grid_kwh: float | None             # + import from upstream, − export
    bus_voltage_pu: Mapping[str, float]         # participant buses (reward attribution)
    violations: tuple[GridViolation, ...]

class GridModel(Protocol):
    def reset(self, episode_seed: int | None = None, day: str | None = None) -> None: ...
    def assess(self, step: int, injections: Sequence[ParticipantInjection]) -> GridAssessment: ...
    def electrical_distance(self, bus_a: str, bus_b: str) -> float: ...   # along lines, km
    def summary(self) -> NetworkSummary: ...          # plain data for UI and reports
    def topology_view(self) -> TopologyView: ...
```

**Market side (D-05).** Matching becomes lossless: delivered = sold, and there are no path limits in matching. The only grid information the market still uses is `electrical_distance`, for partner preference and distance-based DSO fees. Physical losses appear once, system-wide, in the assessment.

## 6. The step with SimBench (D-01)

```text
actions
 → orders                                   (DERAgent feasibility, ActionHandler)
 → economic matching + DSO residual          (OrderMatcher, lossless;
                                              DSO fees use assessment[t−1])
 → cash + energy + battery settlement        (DERAgent, Battery)
 → injections  (settlement → ParticipantInjection)
 → ONE power flow  (background at t + injections)  → GridAssessment[t]
 → KPIs  (congestion = loading, imbalance = external-grid exchange)
 → reward  (feedback mode: physical-violation term)
 → reputation, next observation (grid block from assessment[t]), info, raw records
```

**Modes** (D-03, a field of the experiment file):

| Mode | Assessment used for | Phase |
|---|---|---|
| `shadow` | Recorded in `info` and raw artifacts only; observations and reward keep the validated definitions | P4 |
| `feedback` | Also in observations (fixed-size grid block) and reward (violation term) | P5 |

**Violation feedback in the reward** (D-11, open):

| Option | Penalty for agent i | Trade-off |
|---|---|---|
| Shared | The same system penalty for all agents | Simple, but weak credit assignment |
| Bus-attributed | A penalty from violations at or electrically near i's bus, plus a share of the system penalty | Matches the paper's `f_contrib` idea. **Recommended.** |
| Marginal | The change in violation when i's injection is removed (an extra power flow per agent) | Most accurate; N+1 power flows per step, so expensive |

**Non-convergence** (D-12, open): for deterministic simulation, fail the run with a clear error. For training, either truncate the episode with a fixed penalty or fail. Never substitute zeros or stale values.

**Observation grid block** (fixed size, independent of the network):

- min and max voltage (pu);
- max line and transformer loading (%);
- losses (kWh);
- external-grid exchange (kWh);
- number of violations;
- the agent's own bus voltage (pu).

Whether the agent's own bus voltage is private or public is an experiment option.

## 7. File-by-file changes to MARLEM (D-04)

These are applied **after** the validated release (P2), in `src_thesis/`, keeping file names:

| File | Change | Phase |
|---|---|---|
| [marketplace/grid/contract_new.py](../../../src_thesis/marketplace/grid/contract_new.py) | Extend as in §5 (rename to `contract.py` when stable) | P3 |
| `marketplace/grid/injection.py` (new) | Settlement → `ParticipantInjection`, with the invariant `net_injection · h = exports − imports` | P3 |
| [adapters/grid/simbench_new.py](../../../src_thesis/adapters/grid/simbench_new.py) | Becomes the pandapower adapter for all network sources (§1–§2, §4–§6); the only module importing `pandapower`, together with the profile source | P3 |
| `adapters/profiles/simbench.py` (new) | Catalog, ownership, scaling, windows, sampler (§3) | P3 |
| [adapters/grid/network.py](../../../src_thesis/adapters/grid/network.py), [marketplace/grid/base.py](../../../src_thesis/marketplace/grid/base.py), [config.py](../../../src_thesis/marketplace/grid/config.py) | **Removed from the tool** (kept in the validated release). `Location` shrinks to participant ID + bus ID. | P3 |
| [marketplace/lem.py](../../../src_thesis/marketplace/lem.py) | Takes `grid_model` and `assessment_mode` from the factory. After settlement: build injections → `assess` → pass to KPIs, reward, observation, info. `reset` forwards the episode day. | P4 |
| [marketplace/market/matching.py](../../../src_thesis/marketplace/market/matching.py) | Remove NetworkX calls (path loss, `update_flow_from_trade`, capacity check); lossless matching; distance from `electrical_distance` | P3 |
| [marketplace/dso/dso.py](../../../src_thesis/marketplace/dso/dso.py) | Congestion and constraint inputs come from `assessment[t−1]`; distance fees use electrical distance; tariffs and residual clearing unchanged | P3, P5 |
| [marketplace/market/order.py](../../../src_thesis/marketplace/market/order.py) | `Trade.transmission_loss` removed (always 0); `distance` = electrical distance | P3 |
| [marl/agents/der.py](../../../src_thesis/marl/agents/der.py) | Location = bus ID; partner distance via `electrical_distance` | P3 |
| [marketplace/observation.py](../../../src_thesis/marketplace/observation.py) | `observation_version`; grid block from the assessment in feedback mode | P5 |
| [marketplace/reward.py](../../../src_thesis/marketplace/reward.py) | `reward_version`; violation term (D-11) | P5 |
| [cooperation/implicit_cooperation.py](../../../src_thesis/cooperation/implicit_cooperation.py) | `grid_congestion` and imbalance from the assessment | P4 |
| [cooperation/metrics/grid_metrics.py](../../../src_thesis/cooperation/metrics/grid_metrics.py) | Rebuilt on the assessment history | P5 |
| [marl/train.py](../../../src_thesis/marl/train.py) | `env_config` carries the experiment file section. Each runner builds its env through the factory. | P6 |

## 8. Open decisions

| Question | Recommendation | Linked issue |
|---|---|---|
| Violation reward attribution (D-11) | Bus-attributed + shared share | C2 (I-42, I-76) |
| Non-convergence in training (D-12) | Truncate with a fixed penalty; flag the episode | — |
| Does reputation keep a grid term? | Yes, from bus-attributed violations; otherwise drop it | I-38 |
| Are DSO congestion fees charged? | Yes, from `assessment[t−1]` loading; fees become real only once I-28 is fixed | I-28, I-70 |
| Partner preference distance | Electrical distance along lines | I-77 |
| Units and Δt | kWh per step for the market; kW for injections; Δt explicit in the experiment file | I-56 |
| Physical `B_grid` | `−external_grid_kwh` replaces the trade-based imbalance | I-23, I-68 |
| Line ratings for `case33bw` | Check whether the "Enhanced IEEE 33-bus" paper provides them; otherwise a documented rule | — |

## 9. Performance (measure in P4)

Measure the following per network and resolution. Compare against the validated release: about 15 ms per `env.step` in `marlem-baseline` for Case 6 after its speed-ups, dominated by blockchain proof-of-work.

- cold and warm `runpp` time;
- deep-copy time;
- full `env.step`;
- memory per env runner;
- throughput for 1, 2, 4 and 6 runners.

If power flow dominates, the levers are: warm-starting `runpp` from the previous step, fewer env runners, or hourly instead of 15-minute resolution.
