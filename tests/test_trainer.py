"""Check every original algorithm/mode configuration before expensive learning."""
import pytest
from scripts.validate_learning import config
from src.environment.train import RLTrainer
from src.environment.base import RLAlgorithm, TrainingMode

@pytest.mark.parametrize('algorithm', list(RLAlgorithm))
@pytest.mark.parametrize('mode', list(TrainingMode))
def test_trainer(algorithm, mode):
    trainer = RLTrainer(config(), algorithm=algorithm, training=mode,
                        iters=2, cpus=1, gpus=0, train_batch_size=32)
    algorithm_config, _ = trainer._setup_config(embeddings_dim=32)
    algorithm_config.validate()
    env = trainer.env
    obs, info = env.reset(seed=7)
    for step in range(8):
        controls = ({id: space.sample() for id, space in env.action_spaces.items()}
                    if mode == TrainingMode.DTDE else env.action_space.sample())
        obs, reward, terminated, truncated, info = env.step(controls)
    assert (terminated['__all__'] if isinstance(terminated, dict) else terminated)
    assert not (truncated['__all__'] if isinstance(truncated, dict) else truncated)
    env.close()
