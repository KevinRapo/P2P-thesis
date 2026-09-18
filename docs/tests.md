# Test documentation

This describes the actual test suite in `tests/`. Run the full suite with:

```powershell
pytest -q
```

This is the acceptance gate for the restored baseline: **69 passed, 0 failed, 0 errors** in the current `marlem` environment (the exact count can increase as regression tests are added). There is no restrictive `pytest.ini` narrowing collection — every file below is collected and run. `tests/test_checkpoint.py` and `tests/test_inference.py` perform real, short RLlib training/restore/inference runs and take the bulk of the ~5 minute total runtime; the rest are fast unit/component tests.

`tests/conftest.py` makes the repository root importable and provides the session-scoped `trained_case` fixture (used by `test_checkpoint.py`/`test_inference.py`) that trains one short real checkpoint per requested mode via `scripts/validate_learning.py`.

## Per-module tests

| File | Covers |
|---|---|
| `test_action.py` | `ActionHandler` — action space construction and per-agent action validation. |
| `test_analytics.py` | The analytics modules (coordination/DSO/grid/market metrics) — that reported values are derived from actual recorded settlement data, not unsupported proxies. |
| `test_battery.py` | `Battery` — SOC tracking, charge/discharge efficiency, and boundary clipping. |
| `test_checkpoint.py` | End-to-end restore-and-continue: trains a real short checkpoint (via the `trained_case` fixture), then exercises `RLTrainer.restore_experiment`/`train_checkpoint` against it. |
| `test_der.py` | `DERAgent` — generation/demand profile integration with battery dispatch. |
| `test_dso.py` | `DSOAgent` — tariff/utility price handling and constructor validation. |
| `test_environment.py` | `LocalEnergyMarket` — the core Gymnasium multi-agent environment (reset/step contract). |
| `test_grid_network.py` | `GridNetwork` — topology construction, node/edge validation, agent placement. |
| `test_implicit_cooperation.py` | `ImplicitCooperation` — the market-health KPI computation used by observations and the reward's cooperation factor. |
| `test_inference.py` | Real learned-policy restoration and repeatable evaluation, parametrized across `dtde`/`ctde`/`ctce`. |
| `test_matching.py` | `OrderMatcher` — order matching and market-clearing settlement. |
| `test_mechanism.py` | The pricing mechanisms (`AVERAGE`, `BUYER`, `SELLER`, `BID_ASK_SPREAD`, `NASH_BARGAINING`, `PROPORTIONAL_SURPLUS`) via their unified `calculate_price` interface. |
| `test_observation.py` | `ObservationHandler` — observation space construction and per-step observation assembly. |
| `test_profile.py` | `DERProfileHandler`/`DSOProfileHandler`/`ProfileHandler` — profile generation, CSV replay, and the `file_profile_mode` ("price" vs. "normalized") distinction. |
| `test_reputation.py` | `ReputationHandler` — agent reputation scoring from trade fulfillment and fairness. |
| `test_restoration_kernel.py` | The physical/economic invariant suite: energy and cash conservation, battery dispatch accounting, network flow limits, profile/config isolation across environment instances, public cooperation signals, reward response to physical outcomes, and preferred-partner allocation. This is the closest thing to a formal specification test for the restoration. |
| `test_reward.py` | `RewardHandler` — the reward formula (Eq. 3–6 in the framework paper: base components, cooperation factor, contribution factor, sign-preserving log compression). |
| `test_trainer.py` | Every original algorithm × training-mode combination (PPO/APPO/SAC × DTDE/CTDE/CTCE) builds and takes one real training step, before any expensive full-length run is attempted. |
| `test_validator.py` | `Validator` — the hash-chained settlement log (tamper-evident logging, not decentralized consensus — see `docs/validation-fix-plan.md` P3-01). |
| `test_visualization.py` | The visualization module — trading network, price/volume, spatial distribution, and KPI figure generation. |

## Other validation entry points

- `scripts/validate_learning.py` — trains one short real checkpoint for a given algorithm/mode and asserts actor parameters actually changed and restored inference uses them. Example: `python scripts/validate_learning.py --algorithm sac --mode ctde`.
- `scripts/validate_notebooks.py` — executes one or more notebooks headlessly and checks for figure/output generation.
- **Do not use `jupyter nbconvert --execute`** for notebook validation on this machine — it dispatches to a `jupyter-nbconvert` executable resolved via PATH, which resolves to a broken environment here and silently reports success on failure. Notebooks in this repo were validated with a direct `nbformat`/`nbclient.NotebookClient` harness instead (see `notebooks/README.md` for the harness snippet).

## Related documents

The test count in this document is illustrative rather than a hard-coded
contract; run the complete suite and report the installed-version count.
Analytics tests currently provide smoke coverage only and should not be cited
as validation of unsupported economic metrics.

- `docs/validation-fix-plan.md` — the defect-by-defect audit and fix record for this restoration, including the paper correspondence for each fix and the known gaps not yet addressed.
- `docs/training-benchmarks.md` — measured real-training wall-clock costs on this hardware.
- `docs/guidelines.md` — coding guidelines.
- `notebooks/README.md` — how to run the case-study notebooks.
