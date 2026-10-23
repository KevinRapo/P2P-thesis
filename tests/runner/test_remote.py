"""The cluster over SSH (``core/runner/remote.py``) without a network: the commands it
sends and how it reads the answers, the fresh copy of a folder over SFTP, and the
connection plumbing (one connection, closed when an operation fails, errors as
``RemoteError``) against a fake asyncssh connection on the real background thread.
Nothing connects anywhere.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import stat
from pathlib import Path

import asyncssh
import pytest

from core.runner import remote
from core.runner.remote import Remote, RemoteError


# --------------------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------------------
def test_shell_path_keeps_the_tilde_open_and_quotes_the_rest():
    assert remote.shell_path("~/marlem-slurm") == "~/marlem-slurm"
    assert remote.shell_path("~/my repo") == "~/'my repo'"
    assert remote.shell_path("~") == "~"
    assert remote.shell_path("/home/u/x y") == "'/home/u/x y'"
    assert remote.shell_path("/opt/python") == "/opt/python"
    assert remote.shell_path("~/a; rm -rf x") == "~/'a; rm -rf x'"


def test_runner_command_quotes_every_argument():
    command = remote.runner_command(
        "~/marlem-slurm",
        "~/miniforge3/envs/marlem/bin/python",
        ["start", "experiments/smoke.json", "--target", "taltech", "--profile", "test"],
    )
    assert command == (
        "cd ~/marlem-slurm && ~/miniforge3/envs/marlem/bin/python -m core.runner "
        "start experiments/smoke.json --target taltech --profile test --json"
    )
    odd = remote.runner_command("~/r", "python", ["stop", "a b", "x; reboot", "$HOME"])
    assert odd.endswith("-m core.runner stop 'a b' 'x; reboot' '$HOME' --json")


def test_sftp_paths_start_in_the_home_directory():
    assert remote.sftp_path("~/marlem-slurm", "runs/x") == "marlem-slurm/runs/x"
    assert remote.sftp_path("~", "runs/x") == "runs/x"
    assert remote.sftp_path("/scratch/repo", "runs/x") == "/scratch/repo/runs/x"


# --------------------------------------------------------------------------------------
# A fake connection on the real loop thread
# --------------------------------------------------------------------------------------
class FakeSFTP:
    """A remote file tree: ``files`` maps a path to ``(content, mtime)``. A path in
    ``broken`` fails when it is copied."""

    def __init__(self, files: dict[str, tuple[bytes, int]]) -> None:
        self.files = files
        self.broken: set[str] = set()
        self.gets: list[tuple[str, bool]] = []

    async def readdir(self, folder: str):
        prefix = folder.rstrip("/") + "/"
        names = {}

        for path, (data, mtime) in self.files.items():
            if path.startswith(prefix):
                first, _, rest = path[len(prefix) :].partition("/")
                if rest:
                    names[first] = asyncssh.SFTPAttrs(permissions=stat.S_IFDIR | 0o755)
                else:
                    names[first] = asyncssh.SFTPAttrs(
                        size=len(data), mtime=mtime, permissions=stat.S_IFREG | 0o644
                    )

        if not names:
            raise asyncssh.SFTPNoSuchFile(f"no such folder {folder}")

        names["link"] = asyncssh.SFTPAttrs(permissions=stat.S_IFLNK | 0o777)
        entries = [asyncssh.SFTPName(n, attrs=a) for n, a in names.items()]
        dot = asyncssh.SFTPAttrs(permissions=stat.S_IFDIR | 0o755)

        return [*entries, asyncssh.SFTPName(".", attrs=dot)]

    async def get(self, source: str, target: str, preserve: bool = False) -> None:
        if source in self.broken:
            raise asyncssh.SFTPFailure(f"cannot read {source}")

        data, mtime = self.files[source]
        Path(target).write_bytes(data)

        if preserve:
            os.utime(target, (mtime, mtime))

        self.gets.append((source, preserve))


class FakeConnection:
    """What ``asyncssh.connect`` returns: answers ``run`` from a queue of results (an
    exception in it is raised)."""

    def __init__(self, results=(), sftp: FakeSFTP | None = None) -> None:
        self.results = list(results)
        self.commands: list[str] = []
        self.run_options: list[dict] = []
        self.sftp = sftp
        self.closed = False

    async def run(self, command, **options):
        self.commands.append(command)
        self.run_options.append(options)
        result = self.results.pop(0)

        if isinstance(result, BaseException):
            raise result

        status, out, err = result

        return asyncssh.SSHCompletedProcess(
            None, command, None, status, None, status, out, err
        )

    @contextlib.asynccontextmanager
    async def _sftp_client(self):
        yield self.sftp

    def start_sftp_client(self):
        return self._sftp_client()

    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


@pytest.fixture()
def connections(monkeypatch):
    """Replace ``asyncssh.connect``: each call returns the next of ``queue`` (an
    exception in it is raised); ``calls`` records the arguments."""

    class Connections:
        queue: list = []
        calls: list = []

    async def connect(host, **options):
        Connections.calls.append((host, options))
        found = Connections.queue.pop(0)

        if isinstance(found, BaseException):
            raise found

        return found

    monkeypatch.setattr(remote.asyncssh, "connect", connect)

    return Connections


@pytest.fixture()
def cluster():
    box = Remote("taltech", "~/marlem-slurm", "~/py/bin/python")
    yield box
    box.close()


def test_nothing_connects_or_starts_until_the_first_call(cluster, connections):
    assert cluster._thread is None and cluster._loop is None
    assert connections.calls == []
    cluster.close()  # closing what never opened is fine


def test_one_connection_serves_every_call(cluster, connections):
    conn = FakeConnection([(0, "a", ""), (3, "b", "e")])
    connections.queue = [conn]
    assert cluster.execute("one") == (0, "a", "")
    assert cluster.execute("two") == (
        3,
        "b",
        "e",
    )  # a status is an answer, not an error
    assert conn.commands == ["one", "two"]
    host, options = connections.calls[0]
    assert (host, len(connections.calls)) == ("taltech", 1)
    assert options == {"keepalive_interval": 30, "connect_timeout": 15}
    assert conn.run_options[0]["check"] is False


# --------------------------------------------------------------------------------------
# Failures: one error type, the connection closed, nothing retried
# --------------------------------------------------------------------------------------
def test_a_lost_connection_is_an_error_and_the_next_call_reconnects(
    cluster, connections
):
    first = FakeConnection([asyncssh.ConnectionLost("gone")])
    second = FakeConnection([(0, "back", "")])
    connections.queue = [first, second]

    with pytest.raises(RemoteError, match=r"^command failed on taltech: gone$"):
        cluster.execute("x")

    assert first.closed and first.commands == ["x"]  # not tried again
    assert len(connections.calls) == 1
    assert cluster.execute("y") == (0, "back", "")
    assert len(connections.calls) == 2 and not second.closed


def test_a_connection_that_closed_by_itself_is_replaced(cluster, connections):
    first = FakeConnection([(0, "a", "")])
    second = FakeConnection([(0, "b", "")])
    connections.queue = [first, second]
    cluster.execute("x")
    first.closed = True  # a keepalive failed
    assert cluster.execute("y") == (0, "b", "")


def test_an_unreachable_cluster_suggests_the_vpn(cluster, connections):
    connections.queue = [OSError(11001, "getaddrinfo failed")]

    with pytest.raises(RemoteError, match=r"failed on taltech.*getaddrinfo.*VPN"):
        cluster.execute("x", "git status")

    connections.queue = [TimeoutError()]

    with pytest.raises(RemoteError, match=r"no answer within 135 s.*VPN"):
        cluster.execute("x")

    connections.queue = [asyncssh.PermissionDenied("Permission denied")]

    with pytest.raises(RemoteError, match=r"Permission denied.*VPN"):
        cluster.execute("x")


def test_the_operation_is_named_in_the_message(cluster, connections):
    connections.queue = [FakeConnection([asyncssh.ConnectionLost("gone")])]
    with pytest.raises(RemoteError, match="^git status failed on taltech: gone$"):
        cluster.execute("git status", "git status")


def test_a_failure_on_an_open_connection_has_no_vpn_hint(cluster, connections):
    refused = asyncssh.ChannelOpenError(2, "open failed")
    conn = FakeConnection([refused])
    connections.queue = [conn]

    with pytest.raises(RemoteError) as error:
        cluster.execute("x")

    assert str(error.value) == "command failed on taltech: open failed"
    assert conn.closed


def test_a_bug_is_not_dressed_up_as_a_remote_error(cluster, connections):
    connections.queue = [FakeConnection([ValueError("a bug")])]
    with pytest.raises(ValueError, match="a bug"):
        cluster.execute("x")


# --------------------------------------------------------------------------------------
# runner: the JSON protocol
# --------------------------------------------------------------------------------------
def test_runner_sends_the_command_and_reads_the_json(cluster, connections):
    conn = FakeConnection([(0, '{"experiments": []}\n', "")])
    connections.queue = [conn]
    assert cluster.runner("status", "--target", "taltech") == {"experiments": []}
    assert conn.commands[0] == (
        "cd ~/marlem-slurm && ~/py/bin/python -m core.runner "
        "status --target taltech --json"
    )


def test_runner_sends_its_input_to_standard_input(cluster, connections):
    conn = FakeConnection([(0, '{"experiment": "x"}', ""), (0, "{}", "")])
    connections.queue = [conn]
    assert cluster.runner("start", "-", input='{"name": "x"}') == {"experiment": "x"}
    assert conn.run_options[0]["input"] == '{"name": "x"}'
    cluster.runner("status")
    assert conn.run_options[1]["input"] is None


def test_a_failure_with_a_json_error_becomes_that_error(cluster, connections):
    out = '{"error": "no experiment \'x\' in runs"}'
    connections.queue = [FakeConnection([(2, out, "")])]

    with pytest.raises(RemoteError) as error:
        cluster.runner("stop", "x")

    assert str(error.value) == "no experiment 'x' in runs"


def test_a_failure_without_json_quotes_the_status_and_the_end_of_stderr(
    cluster, connections
):
    stderr = "noise\n" * 500 + "bash: python: command not found"
    connections.queue = [FakeConnection([(127, "", stderr), (1, "", "")])]

    with pytest.raises(RemoteError) as error:
        cluster.runner("status")

    message = str(error.value)
    assert message.startswith("runner status failed on taltech: exit status 127")
    assert message.endswith("command not found")
    assert len(message) < remote.TAIL_CHARS + 100

    with pytest.raises(RemoteError, match="exit status 1: no output"):
        cluster.runner("status")


def test_output_that_is_not_json_is_an_error_even_on_exit_0(cluster, connections):
    banner = "Welcome to the cluster\n" + '{"a": 1}'
    connections.queue = [FakeConnection([(0, banner, ""), (0, "[1, 2]", "")])]

    with pytest.raises(RemoteError, match="printed no JSON.*Welcome"):
        cluster.runner("status")

    with pytest.raises(RemoteError, match="printed no JSON"):
        cluster.runner("status")  # JSON, but not an object


def test_check_may_exit_1_with_its_report(cluster, connections):
    report = '{"ok": false}'
    results = [(1, report, ""), (1, report, ""), (1, '{"error": "boom"}', "")]
    connections.queue = [FakeConnection(results)]
    assert cluster.runner("check", accept=(0, 1)) == {"ok": False}

    with pytest.raises(RemoteError, match="exit status 1"):
        cluster.runner("check")  # exit 1 is not an answer unless accepted

    with pytest.raises(RemoteError, match="^boom$"):  # an error stays an error
        cluster.runner("check", accept=(0,))


def test_head_and_uncommitted_ask_git_in_the_checkout(cluster, connections):
    commit = "0123456789abcdef0123456789abcdef01234567"
    conn = FakeConnection(
        [(0, commit + "\n", ""), (0, "", ""), (0, " M core/x.py\n", "")]
    )
    connections.queue = [conn]
    assert cluster.head() == commit
    assert cluster.uncommitted() is False
    assert cluster.uncommitted() is True
    assert conn.commands[0] == "git -C ~/marlem-slurm rev-parse HEAD"
    assert conn.commands[1] == (
        "git -C ~/marlem-slurm status --porcelain --untracked-files=no"
    )


def test_git_that_fails_is_an_error_not_a_guess(cluster, connections):
    failed = (128, "", "fatal: not a git repository")
    connections.queue = [FakeConnection([failed, failed])]

    with pytest.raises(RemoteError, match=r"git rev-parse failed.*not a git repo"):
        cluster.head()

    with pytest.raises(RemoteError, match=r"git status failed.*exit status 128"):
        cluster.uncommitted()


# --------------------------------------------------------------------------------------
# pull: a fresh copy
# --------------------------------------------------------------------------------------
BASE = "marlem-slurm/runs/x"


def cluster_files() -> dict[str, tuple[bytes, int]]:
    return {
        f"{BASE}/experiment.json": (b'{"name": "x"}', 1000),
        f"{BASE}/slurm.json": (b"{}", 1001),
        f"{BASE}/slurm/job_1.pkl": (b"pickle", 1002),
        f"{BASE}/r1/status.json": (b'{"state": "running"}', 1003),
        f"{BASE}/r1/metrics.csv": (b"a,b\n1,2\n", 1004),
        f"{BASE}/r1/checkpoint/weights.bin": (b"X" * 50, 1005),
        f"{BASE}/r1/deep/checkpoint/more.bin": (b"Y" * 50, 1006),
        f"{BASE}/r1/deep/notes.txt": (b"hi", 1007),
    }


def files_in(folder: Path) -> list[str]:
    return sorted(
        p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()
    )


def test_pull_copies_every_file_but_the_skipped_folders(cluster, connections, tmp_path):
    sftp = FakeSFTP(cluster_files())
    connections.queue = [FakeConnection(sftp=sftp)]
    mirror = tmp_path / "mirror" / "x"
    assert cluster.pull("runs/x", mirror) == 5
    assert files_in(mirror) == [
        "experiment.json",
        "r1/deep/notes.txt",
        "r1/metrics.csv",
        "r1/status.json",
        "slurm.json",  # a file: only folders called slurm are left out
    ]
    assert all(preserve for _, preserve in sftp.gets)  # their mtimes are kept
    assert (mirror / "r1" / "metrics.csv").read_bytes() == b"a,b\n1,2\n"
    assert int((mirror / "r1" / "metrics.csv").stat().st_mtime) == 1004
    assert sorted(p.name for p in mirror.parent.iterdir()) == ["x"]  # no leftovers


def test_a_second_pull_replaces_the_mirror_with_a_fresh_copy(
    cluster, connections, tmp_path
):
    sftp = FakeSFTP(cluster_files())
    connections.queue = [FakeConnection(sftp=sftp)]
    mirror = tmp_path / "x"
    cluster.pull("runs/x", mirror)
    (mirror / "stale.txt").write_text("from an earlier attempt", encoding="utf-8")
    (mirror / "experiment.json").write_bytes(b"damaged")
    del sftp.files[f"{BASE}/r1/deep/notes.txt"]  # gone on the cluster
    sftp.files[f"{BASE}/r1/metrics.csv"] = (b"a,b\n1,2\n3,4\n", 1010)
    sftp.files[f"{BASE}/r2/status.json"] = (b"{}", 1012)
    assert cluster.pull("runs/x", mirror) == 5
    assert files_in(mirror) == [
        "experiment.json",
        "r1/metrics.csv",
        "r1/status.json",
        "r2/status.json",
        "slurm.json",
    ]
    assert (mirror / "experiment.json").read_bytes() == b'{"name": "x"}'
    assert (mirror / "r1" / "metrics.csv").read_bytes() == b"a,b\n1,2\n3,4\n"


def test_a_failed_pull_keeps_the_previous_mirror(cluster, connections, tmp_path):
    sftp = FakeSFTP(cluster_files())
    connections.queue = [FakeConnection(sftp=sftp), FakeConnection(sftp=sftp)]
    mirror = tmp_path / "x"
    cluster.pull("runs/x", mirror)
    before = {name: (mirror / name).read_bytes() for name in files_in(mirror)}
    sftp.files[f"{BASE}/r1/metrics.csv"] = (b"new", 1010)
    sftp.broken.add(f"{BASE}/r1/status.json")  # fails half-way through the copy

    with pytest.raises(RemoteError, match="copying runs/x failed on taltech.*cannot"):
        cluster.pull("runs/x", mirror)

    assert {name: (mirror / name).read_bytes() for name in files_in(mirror)} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x"]  # partial copy removed


def test_pulling_a_missing_folder_fails_and_makes_no_local_folder(
    cluster, connections, tmp_path
):
    connections.queue = [FakeConnection(sftp=FakeSFTP(cluster_files()))]
    with pytest.raises(RemoteError, match="copying runs/missing failed on taltech"):
        cluster.pull("runs/missing", tmp_path / "mirror" / "missing")
    assert list((tmp_path / "mirror").iterdir()) == []


def test_a_leftover_partial_copy_does_not_get_into_the_mirror(
    cluster, connections, tmp_path
):
    connections.queue = [FakeConnection(sftp=FakeSFTP(cluster_files()))]
    leftover = tmp_path / ".x.partial"
    leftover.mkdir()
    (leftover / "junk.txt").write_text("from a crashed pull", encoding="utf-8")
    cluster.pull("runs/x", tmp_path / "x")
    assert "junk.txt" not in files_in(tmp_path / "x")
    assert not leftover.exists()


def test_a_failed_replacement_puts_the_old_mirror_back(tmp_path, monkeypatch):
    mirror, fresh = tmp_path / "x", tmp_path / ".x.partial"
    mirror.mkdir()
    (mirror / "old.txt").write_text("old", encoding="utf-8")
    fresh.mkdir()
    real_rename = Path.rename

    def rename(self, target):
        if self == fresh:
            raise PermissionError("in use")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)

    with pytest.raises(PermissionError):
        remote.replace_folder(fresh, mirror)

    assert (mirror / "old.txt").read_text(encoding="utf-8") == "old"


def test_copy_tree_walks_one_file_after_the_other(tmp_path):
    sftp = FakeSFTP(cluster_files())
    count = asyncio.run(remote.copy_tree(sftp, BASE, tmp_path / "x", remote.PULL_SKIP))
    assert count == 5
    assert [source.removeprefix(BASE + "/") for source, _ in sftp.gets] == [
        "experiment.json",
        "r1/deep/notes.txt",
        "r1/metrics.csv",
        "r1/status.json",
        "slurm.json",
    ]


# --------------------------------------------------------------------------------------
# Closing
# --------------------------------------------------------------------------------------
def test_close_stops_the_thread_and_the_object_can_be_used_again(cluster, connections):
    first = FakeConnection([(0, "a", "")])
    second = FakeConnection([(0, "b", "")])
    connections.queue = [first, second]
    cluster.execute("x")
    thread = cluster._thread
    assert thread is not None and thread.is_alive() and thread.daemon
    cluster.close()
    assert first.closed and not thread.is_alive() and cluster._thread is None
    assert cluster.execute("y") == (0, "b", "")
    assert cluster._thread is not thread


def test_it_works_as_a_context_manager(connections):
    conn = FakeConnection([(0, "a", "")])
    connections.queue = [conn]

    with Remote("taltech", "~/r", "python") as box:
        assert box.execute("x")[0] == 0

    assert conn.closed and box._thread is None
