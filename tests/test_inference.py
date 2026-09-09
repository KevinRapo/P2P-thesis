"""Restore real learned policies and check repeatable complete evaluations."""
import pytest
from src.environment.inference import RLInference

@pytest.mark.parametrize('trained_case', ['dtde', 'ctde', 'ctce'], indirect=True)
def test_inference(trained_case):
    config, evidence = trained_case
    model = RLInference(config, checkpoint_path=evidence['checkpoint'], exploration=False)
    try:
        observations, _ = model.env.reset(seed=19)
        first = model._compute_actions(observations)
        observations, _ = model.env.reset(seed=19)
        second = model._compute_actions(observations)
        import tree
        import numpy as np
        for left, right in zip(tree.flatten(first), tree.flatten(second)):
            np.testing.assert_array_equal(left, right)
        results = model.inference(iters=1)
        assert results
        assert evidence['changed_actor_parameters']
    finally:
        model.close()
