# Experiment protocol

Use declared, non-overlapping scenario identifiers and seed lists. Do not use
a training scenario or seed to select a checkpoint and report it as test data.

```python
from src.environment.experiment import ScenarioSplit, run_declared_training

split = ScenarioSplit(
    train_ids=("profile-set-a",),
    validation_ids=("profile-set-b",),
    test_ids=("profile-set-c",),
    training_seeds=(101, 102, 103),
    evaluation_seeds=(201,),
    test_seeds=(301,),
)

# The factory must build an independently seeded RLTrainer for the declared
# scenario ID and seed, with a distinct result directory per call.
completed_runs = run_declared_training(build_trainer, split, "profile-set-a")
print(split.fingerprint())  # Record this alongside the run manifest.
```

Select a checkpoint using only validation scenarios. Afterwards, call
`run_declared_episodes` once for a declared test scenario and append its raw
records to that test run's `episode_records.jsonl`. The declared reset seed
also controls the `random_valid_actions` baseline when it is used as the policy.

For every reported comparison, retain its `run_manifest.json` (including its
`manifest_sha256`) and JSONL records. The split fingerprint and manifest hash
identify the exact scenario declaration and run inputs without selecting a
best seed. Before analysing or publishing a run, call
`RLTrainer.verify_run_manifest(path)`; it returns `False` if any manifest
content has changed after creation.
Use `EpisodeRecordStore.summarize` over the raw records to report count, mean,
sample standard deviation, and the 95% normal-approximation interval. A
single-seed result is a smoke test, not a comparison result.

## Minimal end-to-end check

Before a real training study, run the three-seed, non-learning protocol smoke:

```powershell
python -m src.environment.reproducibility_smoke
```

It creates a new ignored directory under `tmp/` containing a verified manifest
and `episode_records.jsonl`, then prints the split fingerprint and return
summary. It validates the workflow only; it is not a scientific comparison.

## Bundled-data limitation

The bundled 60-minute generation and demand files contain named profile columns
but no timestamp/day identifier. The bundled `fit_60min.csv` and
`utility_60min.csv` files also have no column pair satisfying the model
contract `feed_in_tariff <= utility_price` at every step. Do not label their
columns as chronological held-out days or use those raw tariff pairs in a
reported study. Supply validated tariff/day data, or declare a synthetic DSO
tariff in the manifest when using the named generation/demand profiles.
