"""Settings from a .env file: read once, never overriding the real environment."""

from src_thesis.env import load_env


def test_env_file_fills_unset_variables_only(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nMARLEM_TEST_A=from-file\nMARLEM_TEST_B=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MARLEM_TEST_A", raising=False)
    monkeypatch.setenv("MARLEM_TEST_B", "from-environment")
    assert load_env(env)
    import os

    assert os.environ["MARLEM_TEST_A"] == "from-file"
    assert os.environ["MARLEM_TEST_B"] == "from-environment"  # the environment wins
    monkeypatch.delenv("MARLEM_TEST_A")


def test_missing_env_file_is_fine(tmp_path) -> None:
    assert load_env(tmp_path / "missing.env") is False
