"""Exercise the original experiment restoration and continuation workflows."""
from pathlib import Path
import pytest
from src.environment.train import RLTrainer
from src.environment.base import RLAlgorithm, TrainingMode

@pytest.mark.parametrize('trained_case', ['dtde'], indirect=True)
def test_restore_and_continue(trained_case):
    config, evidence = trained_case
    checkpoint = Path(evidence['checkpoint'])
    trainer = RLTrainer(config, algorithm=RLAlgorithm.PPO, training=TrainingMode.DTDE,
                        iters=2, checkpoint_freq=1, cpus=1, gpus=0, train_batch_size=32,
                        storage_path=str(checkpoint.parents[2]))
    restored, _ = trainer.restore_experiment(str(checkpoint.parents[1]), embeddings_dim=32)
    original_iteration = restored.get_best_result().metrics['training_iteration']
    continued, _ = trainer.train_checkpoint(str(checkpoint), iters=2, embeddings_dim=32)
    result = continued.get_best_result()
    assert continued.num_errors == 0
    # Inspect the final row, since the best-reward row may be earlier.
    import json
    final = json.loads((Path(result.path) / 'result.json').read_text().splitlines()[-1])
    assert final['iterations_since_restore'] == 2
    assert final['training_iteration'] == original_iteration + 2
    assert result.checkpoint is not None
