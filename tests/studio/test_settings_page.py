"""The Settings page's folder dialog: what it is asked and what it hands back."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from studio.adapters import workspace
from studio.pages import settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def finished(monkeypatch, returncode=0, stdout="", stderr="") -> list:
    """Replace the dialog's process with one that ends at once; the calls are kept."""
    calls: list = []

    def run(command, **_):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(workspace.subprocess, "run", run)
    return calls


def test_browsing_starts_at_the_closest_folder_that_exists(tmp_path):
    assert workspace.nearest_folder(tmp_path / "a" / "b") == tmp_path.resolve()


def test_the_dialog_opens_there_and_hands_back_the_folder(monkeypatch, tmp_path):
    calls = finished(monkeypatch, stdout="D:/data/marlem\n")

    assert workspace.choose_folder(tmp_path / "gone", "Title") == Path("D:/data/marlem")
    assert calls[0][-2:] == [str(tmp_path.resolve()), "Title"]


def test_a_cancelled_dialog_is_no_folder(monkeypatch, tmp_path):
    finished(monkeypatch, stdout="\n")

    assert workspace.choose_folder(tmp_path) is None


def test_a_dialog_that_cannot_open_says_why(monkeypatch, tmp_path):
    finished(monkeypatch, returncode=1, stderr="Traceback\nTclError: no display\n")

    with pytest.raises(OSError, match="no display"):
        workspace.choose_folder(tmp_path)


@pytest.mark.anyio
async def test_the_browse_button_fills_the_field(monkeypatch, tmp_path):
    folder = tmp_path / "chosen"
    monkeypatch.setattr(workspace, "choose_folder", lambda *_: folder)

    async with user_simulation(settings._workspace_section) as user:
        await user.open("/")
        user.find(marker="browse").click()
        await user.should_see(kind=ui.input, content=str(folder))
