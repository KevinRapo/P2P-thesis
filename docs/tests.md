# Test guide

Run the maintained validation gate from the repository root:

```powershell
uv run pytest -q
```

The test configuration collects the focused `test_p[0-3]_*.py` suites. They are
small, deterministic regression tests for the validation-fix plan:

- `test_p0_*`: transaction kernel, action feasibility, battery accounting,
  episode horizon, reset isolation, and declared agent ordering.
- `test_p1_*`: grid flow constraints, DSO residuals, observation leakage,
  reputation updates, units, and the price-time market baseline.
- `test_p2_*`: exact CSV replay, configuration round trips, split/manifest
  identities, and training-run configuration safeguards.
- `test_p3_*`: defensive input validation, optional settlement logging, and
  notebook path/unit-contract checks.

The other `tests/test_*.py` modules are retained as legacy smoke-test material
but are not part of the acceptance gate until each is updated to the current
model contract. Add new validation regressions to the appropriately numbered
focused suite and keep them deterministic.
