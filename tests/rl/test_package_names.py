"""``core.rl``'s public names are the functions and classes, not the submodules of
the same name: ``train`` is the function even after ``core.rl.train`` (the module)
was imported, as the runner's jobs do."""

import core.rl.train  # noqa: F401  (the module first, as RunSpec.run does)
from core.rl import Run, train


def test_train_is_the_function_after_the_module_was_imported():
    assert callable(train) and train.__module__ == "core.rl.train"
    assert isinstance(Run, type)
