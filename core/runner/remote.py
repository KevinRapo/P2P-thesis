"""The cluster as seen from this machine: one SSH connection (asyncssh) to its login
node, kept open on a private background event-loop thread.

The methods of ``Remote`` are synchronous, so the same object works from the command
line, from Jupyter (whose event loop is already running; ours is another one, in a
thread of its own) and from the Studio (called from a thread, like its other
services):

    execute(command)             run a shell command: (exit status, stdout, stderr)
    runner(*args)                run ``python -m core.runner <args> --json`` in the
                                 cluster's checkout of the repository; its JSON answer
    head() / uncommitted()       the checkout's commit / whether it has changes
    pull(remote_dir, local_dir)  a fresh copy of a folder of the checkout here
    close()                      close the connection and stop the thread

The connection is opened by the first call and reused by the next ones. Nothing is
retried: when an operation fails the connection is closed and ``RemoteError`` says
what failed, on which host and why; the next call opens a new connection. Your ssh
configuration is read as ssh does, so ``host`` is the alias there (address, user,
key). No password or agent is involved: the key file is used.

Import this module where it is used: it loads asyncssh, which the cluster's own
environment does not need.
"""

from __future__ import annotations

import asyncio
import json
import posixpath
import shlex
import shutil
import stat
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence

import asyncssh

# Folders ``pull`` leaves on the cluster: checkpoints are large, ``slurm/`` holds
# submitit's pickles and batch scripts.
PULL_SKIP = ("checkpoint", "slurm")
PULL_TIMEOUT_S = 900
TAIL_CHARS = 600  # how much of a failed command's output goes into the message
# What asyncssh, the network and the clock raise; anything else is a bug and passes.
_FAILURES = (asyncssh.Error, OSError, EOFError, TimeoutError)


class RemoteError(RuntimeError):
    """An operation on the cluster failed, or the cluster cannot be reached; the
    message says which and carries the cluster's own error text."""


# --------------------------------------------------------------------------------------
# What is sent to the cluster
# --------------------------------------------------------------------------------------
def shell_path(path: str) -> str:
    """``path`` for the cluster's shell: a leading ``~`` stays unquoted, so the shell
    expands it; the rest is quoted (``~/my repo`` -> ``~/'my repo'``)."""
    if path == "~" or path == "~/":
        return path
    if path.startswith("~/"):
        return "~/" + shlex.quote(path[2:])
    return shlex.quote(path)


def runner_command(repo: str, python: str, args: Sequence[str]) -> str:
    """The shell command that runs the runner's CLI in the checkout, asking for JSON."""
    quoted = " ".join(shlex.quote(arg) for arg in args)
    run = f"{shell_path(python)} -m core.runner {quoted} --json"
    return f"cd {shell_path(repo)} && {run}"


def sftp_path(repo: str, folder: str) -> str:
    """A folder of the repository as SFTP wants it: relative paths start in the home
    directory, so ``~/marlem-slurm`` and ``runs/x`` give ``marlem-slurm/runs/x``."""
    if repo == "~":
        base = ""
    else:
        base = repo[2:] if repo.startswith("~/") else repo
    return posixpath.join(base, folder) if base else folder


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    """The end of a command's output, for an error message."""
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _reason(error: BaseException, limit: float) -> str:
    if isinstance(error, TimeoutError):
        return f"no answer within {limit:g} s"
    return getattr(error, "reason", None) or str(error) or type(error).__name__


# --------------------------------------------------------------------------------------
# Copying a folder over SFTP
# --------------------------------------------------------------------------------------
async def copy_tree(sftp: Any, folder: str, local: Path, skip: Sequence[str]) -> int:
    """Copy every file under ``folder`` on the cluster (an SFTP path) into ``local``,
    one after the other, leaving out the folders called in ``skip`` at any depth and
    anything that is not a plain file or folder. Modification times are kept.

    Returns:
        The number of files copied.
    """
    local.mkdir(parents=True, exist_ok=True)
    copied = 0
    for entry in sorted(await sftp.readdir(folder), key=lambda e: e.filename):
        name, mode = entry.filename, entry.attrs.permissions or 0
        if name in (".", ".."):
            continue
        source = posixpath.join(folder, name)
        if stat.S_ISDIR(mode):
            if name not in skip:
                copied += await copy_tree(sftp, source, local / name, skip)
        elif stat.S_ISREG(mode):
            await sftp.get(source, str(local / name), preserve=True)
            copied += 1
    return copied


def replace_folder(new: Path, target: Path) -> None:
    """Make ``new`` the folder ``target``, replacing what was there: the old one is
    moved aside first and comes back if the move fails."""
    old = target.with_name(f".{target.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    try:
        new.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)
        raise
    shutil.rmtree(old, ignore_errors=True)


# --------------------------------------------------------------------------------------
# The connection
# --------------------------------------------------------------------------------------
class Remote:
    """The cluster's login node over SSH.

    Args:
        host: The ssh host, usually an alias in ``~/.ssh/config``.
        repo: The repository on the cluster; a leading ``~`` is the cluster home.
        python: The cluster's Python (with the repository's requirements).
        keepalive_s: Seconds between keepalive messages (0: none), so a dead connection
            is noticed instead of hanging.
        connect_timeout_s: How long to wait for the connection to open.
        command_timeout_s: How long one command may run.
    """

    def __init__(
        self,
        host: str,
        repo: str,
        python: str,
        *,
        keepalive_s: float = 30,
        connect_timeout_s: float = 15,
        command_timeout_s: float = 120,
    ) -> None:
        self.host = host
        self.repo = repo
        self.python = python
        self.keepalive_s = keepalive_s
        self.connect_timeout_s = connect_timeout_s
        self.command_timeout_s = command_timeout_s
        self._guard = threading.Lock()  # starting and stopping the loop thread
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        # The two below belong to the loop thread.
        self._connecting: Optional[asyncio.Lock] = None
        self._conn: Optional[asyncssh.SSHClientConnection] = None

    def __enter__(self) -> "Remote":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- Commands ---------------------------------------------------------------------
    def execute(self, command: str, what: str = "command") -> tuple[int, str, str]:
        """Run a shell command on the cluster: ``(exit status, stdout, stderr)``.
        ``what`` names the operation in the error message."""

        async def operation(conn: asyncssh.SSHClientConnection):
            done = await conn.run(command, check=False, errors="replace")
            code = done.returncode if done.returncode is not None else -1
            return code, str(done.stdout or ""), str(done.stderr or "")

        return self._call(what, operation, self.command_timeout_s)

    def runner(self, *args: str, accept: Sequence[int] = (0,)) -> dict:
        """Run ``python -m core.runner <args> --json`` in the cluster's checkout and
        return the JSON object it prints.

        ``accept`` are the exit statuses that carry an answer (``check`` exits 1 with
        its report when the target is not ready). Any other status is a
        ``RemoteError``: with the runner's own message if it printed ``{"error":
        ...}``, else with the status and the end of its output.
        """
        what = f"runner {args[0]}"
        command = runner_command(self.repo, self.python, args)
        status, out, err = self.execute(command, what)
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            data = None
        if status not in accept:
            if data is not None and "error" in data:
                raise RemoteError(str(data["error"]))
            detail = tail(err) or tail(out) or "no output"
            reason = f"exit status {status}: {detail}"
        elif data is None:
            reason = f"it printed no JSON: {tail(out) or 'no output'}"
        else:
            return data
        raise RemoteError(f"{what} failed on {self.host}: {reason}")

    def head(self) -> str:
        """The commit the cluster's checkout is at."""
        return self._git("rev-parse", "HEAD").strip()

    def uncommitted(self) -> bool:
        """Whether the cluster's checkout has changes to tracked files."""
        return bool(self._git("status", "--porcelain", "--untracked-files=no").strip())

    def _git(self, *args: str) -> str:
        what = f"git {args[0]}"
        command = f"git -C {shell_path(self.repo)} {' '.join(args)}"
        status, out, err = self.execute(command, what)
        if status != 0:
            reason = f"exit status {status}: {tail(err) or 'no output'}"
            raise RemoteError(f"{what} failed on {self.host}: {reason}")
        return out

    # --- Files ------------------------------------------------------------------------
    def pull(
        self, remote_dir: str, local_dir: Path, skip: Sequence[str] = PULL_SKIP
    ) -> int:
        """Replace ``local_dir`` with a fresh copy of ``remote_dir`` (relative to the
        repository, e.g. ``runs/smoke``): every file, one after the other, except the
        folders called in ``skip`` at any depth.

        The copy goes into a temporary folder next to ``local_dir`` and takes its place
        only when it is complete. If anything fails the temporary folder is removed and
        the previous ``local_dir`` stays as it was.

        Returns:
            The number of files copied.
        """
        local_dir = Path(local_dir)
        partial = local_dir.with_name(f".{local_dir.name}.partial")
        folder = sftp_path(self.repo, remote_dir)

        async def operation(conn: asyncssh.SSHClientConnection):
            async with conn.start_sftp_client() as sftp:
                return await copy_tree(sftp, folder, partial, tuple(skip))

        shutil.rmtree(partial, ignore_errors=True)
        try:
            count = self._call(f"copying {remote_dir}", operation, PULL_TIMEOUT_S)
            replace_folder(partial, local_dir)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        return count

    # --- Closing ----------------------------------------------------------------------
    def close(self) -> None:
        """Close the connection and stop the thread. The next call opens both again."""
        with self._guard:
            loop, thread = self._loop, self._thread
            self._loop = self._thread = None
        if loop is None or thread is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._disconnect(), loop).result(5)
        except Exception:  # closing must not fail: the thread stops anyway
            pass
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        if not thread.is_alive():
            loop.close()

    # --- The loop thread --------------------------------------------------------------
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._guard:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                self._connecting = asyncio.Lock()
                self._conn = None
                self._thread = threading.Thread(
                    target=self._serve,
                    args=(loop,),
                    name=f"ssh-{self.host}",
                    daemon=True,
                )
                self._thread.start()
                self._loop = loop
            return self._loop

    @staticmethod
    def _serve(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _call(
        self,
        what: str,
        operation: Callable[[Any], Awaitable[Any]],
        timeout: float,
    ) -> Any:
        """Run ``operation(connection)`` on the loop thread and wait for its result."""
        future = asyncio.run_coroutine_threadsafe(
            self._guarded(what, operation, timeout), self._ensure_loop()
        )
        return future.result()

    # --- On the loop thread -----------------------------------------------------------
    async def _guarded(
        self, what: str, operation: Callable[[Any], Awaitable[Any]], timeout: float
    ) -> Any:
        """The one place where a failure becomes a ``RemoteError``: the connection is
        closed, so the next call opens a new one."""
        limit = timeout + self.connect_timeout_s
        try:
            return await asyncio.wait_for(self._use(operation), limit)
        except _FAILURES as error:
            hint = " (is the VPN on?)" if self._conn is None else ""
            self._drop_connection()
            reason = _reason(error, limit)
            raise RemoteError(f"{what} failed on {self.host}: {reason}{hint}") from None

    async def _use(self, operation: Callable[[Any], Awaitable[Any]]) -> Any:
        assert self._connecting is not None
        async with self._connecting:
            if self._conn is None or self._conn.is_closed():
                self._conn = None  # None while connecting: a failure here is "no route"
                self._conn = await asyncssh.connect(
                    self.host,
                    keepalive_interval=self.keepalive_s,
                    connect_timeout=self.connect_timeout_s,
                )
            conn = self._conn
        return await operation(conn)

    def _drop_connection(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()

    async def _disconnect(self) -> None:
        conn = self._conn
        self._drop_connection()
        if conn is not None:
            await conn.wait_closed()
