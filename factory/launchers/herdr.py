"""
The launcher over herdr's CLI (herdr 0.9.5, protocol 22).

Everything here was settled by #215's live run, and the syntax authority is
herdr's own `--help`. Four things are worth knowing before changing it:

- **Every command is an argument list, never a shell string.** A prompt or an
  env value can hold anything.
- **After `agent start`, every command targets the pane id.** A name follows
  whichever agent holds it; the pane id is the one the loop created.
- **Nothing herdr says is guessed at.** An error code this module does not name,
  a reply that is not JSON, and an `agent_status` outside herdr's five each raise
  `LauncherError`. None becomes a `WorkerState`.
- **Only one blocked startup is answered**: the folder-trust dialog, in the one
  layout where `down` then `enter` selects "Yes", and only in a linked worktree
  of this repository. Every other blocked screen fails the start, carrying the
  Handle so the loop can stop the pane.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from factory.launcher import (
    RESUMABLE_ROLE,
    Handle,
    LauncherError,
    WorkerSpec,
    WorkerState,
    check_credentials,
)

#: Map from herdr's `agent_status` to ours, before the prompt-seen rule.
_STATUS: Final = {
    "working": WorkerState.WORKING,
    "unknown": WorkerState.WORKING,
    "idle": WorkerState.FINISHED,
    "done": WorkerState.FINISHED,
    "blocked": WorkerState.BLOCKED,
}

_TRUST_DIALOG: Final = re.compile(
    r"Is this a project you created or one you trust\?"
    r".*?(?:(\d+)\. )?No, exit (?:(\d+)\. )?Yes\b"
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Timeouts:
    """
    How long each herdr wait may take. These are herdr timings, not
    Expectations about the game: they bound a stall, and a wrong value costs an
    attempt rather than a wrong answer.
    """

    agent_start_ms: int = 60_000
    trust_wait_ms: int = 30_000
    agent_prompt_ms: int = 60_000
    stop_wait_s: float = 30.0
    stop_poll_s: float = 0.25


def default_runner(args: Sequence[str]) -> CommandResult:
    """Run herdr for real. Tests replace this and fail if it is reached."""
    try:
        done = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            shell=False,
        )
    except OSError as error:
        raise LauncherError(f"could not run herdr: {error}") from error
    return CommandResult(done.returncode, done.stdout, done.stderr)


def read_process_table() -> dict[int, int]:
    """
    Every running process as pid -> parent pid, from a Toolhelp snapshot.

    Windows only: herdr's pids there are Windows pids. Raises on any other
    platform when called; importing this module never does.
    """
    if sys.platform != "win32":
        raise NotImplementedError("the process table is only read on Windows")
    # Imported here so that importing this module never fails off Windows.
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    th32cs_snapprocess = 0x2
    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot is None or snapshot == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    table: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            table[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return table


def is_linked_worktree(cwd: Path, common_dir: Path) -> bool:
    """
    Whether `cwd` is a linked worktree of the repository whose git dir is
    `common_dir`, by git's own pairing.

    `cwd/.git` is a file whose `gitdir` is a direct child of
    `<common>/worktrees`, and that child's own `gitdir` file names `cwd/.git`
    back. Paths are compared resolved, never as strings: git writes forward
    slashes even on Windows.
    """
    dot_git = cwd / ".git"
    try:
        if not dot_git.is_file():
            return False
        first = dot_git.read_text(encoding="utf-8").splitlines()[0]
        prefix = "gitdir:"
        if not first.startswith(prefix):
            return False
        admin = _resolve(Path(first[len(prefix) :].strip()), cwd)
        if admin.parent != (common_dir / "worktrees").resolve():
            return False
        pointer = (admin / "gitdir").read_text(encoding="utf-8").splitlines()[0]
        return _resolve(Path(pointer.strip()), admin) == dot_git.resolve()
    except OSError, IndexError, ValueError:
        return False


def _resolve(path: Path, relative_to: Path) -> Path:
    return (path if path.is_absolute() else relative_to / path).resolve()


def trust_dialog_matches(text: str) -> bool:
    """
    Whether `text` is Claude Code's folder-trust dialog in the layout where
    `down` then `enter` selects "Yes".

    That is: the question, then "No, exit", then, with only whitespace between,
    "Yes". Anything between the two options, including a cursor marker on the
    Yes option, disqualifies the screen. The live screen (herdr 0.9.5) does not
    number its options; if either is numbered, both must be and be consecutive.
    The text is whitespace-normalised first, so wrapping cannot hide it.
    """
    found = _TRUST_DIALOG.search(" ".join(text.split()))
    if found is None:
        return False
    no_number, yes_number = found.groups()
    if no_number is None and yes_number is None:
        return True
    if no_number is None or yes_number is None:
        return False
    return int(yes_number) == int(no_number) + 1


class HerdrLauncher:
    """
    A `Launcher` over the herdr CLI.

    `_started` is this process's record of the Handles it returned, by name. It
    is checked before `agent get`, which is what makes a second `start` on the
    same launcher return an equal Handle (the prompt was seen to start), while
    a fresh launcher finds the agent through herdr and marks it not seen.
    """

    def __init__(
        self,
        common_dir: Path,
        *,
        run: Callable[[Sequence[str]], CommandResult] | None = None,
        read_process_table: Callable[[], Mapping[int, int]] | None = None,
        environ: Mapping[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        timeouts: Timeouts | None = None,
    ) -> None:
        self._common_dir = common_dir
        self._run = run if run is not None else default_runner
        self._read_table = (
            read_process_table if read_process_table is not None else _default_table()
        )
        self._environ = environ if environ is not None else os.environ
        self._sleep = sleep
        self._monotonic = monotonic
        self._timeouts = timeouts or Timeouts()
        self._started: dict[str, Handle] = {}
        self._stopped: set[str] = set()

    # --- the protocol ---------------------------------------------------------

    def start(self, spec: WorkerSpec) -> Handle:
        check_credentials(spec, self._common_dir)
        if spec.name in self._started:
            return self._started[spec.name]
        role = spec.env.get("FACTORY_ROLE", "")
        found = self._find(spec.name)
        if found is not None:
            handle = Handle(spec.name, found, role, False)
            self._started[spec.name] = handle
            return handle
        pane_id = self._split(spec)
        handle = Handle(spec.name, pane_id, role, False)
        try:
            self._start_agent_and_prompt(spec, handle)
        except LauncherError as error:
            raise LauncherError(str(error), handle=handle, code=error.code) from error
        started = replace(handle, prompt_started=True)
        self._started[spec.name] = started
        return started

    def status(self, handle: Handle) -> WorkerState:
        if handle.pane_id in self._stopped:
            return WorkerState.GONE
        try:
            agent = self._agent(handle.pane_id)
        except LauncherError as error:
            if error.code == "agent_not_found":
                return WorkerState.GONE
            raise
        state = _STATUS.get(_status_of(agent))
        if state is None:
            raise LauncherError(
                f"agent_status {_status_of(agent)!r} is not one of herdr's"
            )
        if state is WorkerState.FINISHED and not handle.prompt_started:
            return WorkerState.BLOCKED
        return state

    def session_id(self, handle: Handle) -> str | None:
        result = self._call(["agent", "list"])
        for entry in result.get("agents", []):
            if entry.get("pane_id") != handle.pane_id:
                continue
            session = entry.get("agent_session")
            if isinstance(session, dict) and session.get("kind") == "id":
                value = session.get("value")
                return value if isinstance(value, str) else None
            return None
        return None

    def stop(self, handle: Handle) -> None:
        if handle.role == RESUMABLE_ROLE:
            raise LauncherError(f"never stop a designer ({handle.name!r})")
        if handle.pane_id == self._environ.get("HERDR_PANE_ID"):
            raise LauncherError(f"{handle.pane_id} is the launcher's own pane")
        try:
            result = self._call(["pane", "process-info", "--pane", handle.pane_id])
        except LauncherError as error:
            if error.code == "pane_not_found":
                self._stopped.add(handle.pane_id)
                return
            raise
        info = result.get("process_info", {})
        shell_pid = info.get("shell_pid")
        if not isinstance(shell_pid, int):
            raise LauncherError(f"herdr reported no shell_pid for {handle.pane_id}")
        table = self._read_table()
        if shell_pid not in table:
            raise LauncherError(
                f"shell_pid {shell_pid} is not in the process table, so the tree "
                "cannot be followed"
            )
        tracked = {shell_pid}
        for process in info.get("foreground_processes", []):
            pid = process.get("pid")
            if isinstance(pid, int):
                tracked.add(pid)
        tracked |= _descendants(table, tracked)
        try:
            self._call(["pane", "close", handle.pane_id])
        except LauncherError as error:
            if error.code != "pane_not_found":
                raise
        self._wait_for_exit(tracked)
        self._stopped.add(handle.pane_id)

    # --- start ----------------------------------------------------------------

    def _find(self, name: str) -> str | None:
        try:
            agent = self._agent(name)
        except LauncherError as error:
            if error.code == "agent_not_found":
                return None
            raise
        return _pane_of(agent)

    def _split(self, spec: WorkerSpec) -> str:
        command = ["pane", "split", "--no-focus", "--cwd", str(spec.cwd)]
        for key, value in spec.env.items():
            command += ["--env", f"{key}={value}"]
        pane = self._call(command).get("pane")
        pane_id = pane.get("pane_id") if isinstance(pane, dict) else None
        if not isinstance(pane_id, str) or not pane_id:
            raise LauncherError("pane split returned no pane_id")
        return pane_id

    def _start_agent_and_prompt(self, spec: WorkerSpec, handle: Handle) -> None:
        arguments = ["--model", spec.model]
        if spec.resume is not None:
            arguments += ["--resume", spec.resume]
        try:
            self._call(
                [
                    "agent",
                    "start",
                    spec.name,
                    "--kind",
                    "claude",
                    "--pane",
                    handle.pane_id,
                    "--timeout",
                    str(self._timeouts.agent_start_ms),
                    "--",
                    *arguments,
                ]
            )
        except LauncherError as error:
            if error.code != "agent_not_ready":
                raise
            self._answer_trust_dialog(spec, handle)
        self._call(
            [
                "agent",
                "prompt",
                handle.pane_id,
                spec.prompt,
                "--wait",
                "--until",
                "working",
                "--until",
                "blocked",
                "--timeout",
                str(self._timeouts.agent_prompt_ms),
            ]
        )

    def _answer_trust_dialog(self, spec: WorkerSpec, handle: Handle) -> None:
        pane = handle.pane_id
        state = _status_of(self._agent(pane))
        if state != "blocked":
            raise LauncherError(
                f"agent_not_ready, but the agent is {state!r}, not blocked"
            )
        read = self._call(["agent", "read", pane, "--source", "recent-unwrapped"])
        text = read.get("read", {}).get("text", "")
        if not isinstance(text, str) or not trust_dialog_matches(text):
            raise LauncherError(
                "startup is blocked at a screen that is not the trust dialog"
            )
        if not is_linked_worktree(spec.cwd, self._common_dir):
            raise LauncherError(
                f"the trust dialog is up, but {spec.cwd} is not a linked worktree of "
                "this repository"
            )
        self._call(["agent", "send-keys", pane, "down", "enter"])
        self._call(
            [
                "agent",
                "wait",
                pane,
                "--until",
                "idle",
                "--until",
                "done",
                "--until",
                "blocked",
                "--timeout",
                str(self._timeouts.trust_wait_ms),
            ]
        )
        settled = _status_of(self._agent(pane))
        if settled not in ("idle", "done"):
            raise LauncherError(f"after the trust answer the agent is {settled!r}")

    # --- stop -----------------------------------------------------------------

    def _wait_for_exit(self, tracked: set[int]) -> None:
        deadline = self._monotonic() + self._timeouts.stop_wait_s
        while True:
            alive = tracked & set(self._read_table())
            if not alive:
                return
            if self._monotonic() >= deadline:
                raise LauncherError(
                    f"processes still running after the pane was closed: {sorted(alive)}"
                )
            self._sleep(self._timeouts.stop_poll_s)

    # --- herdr ----------------------------------------------------------------

    def _agent(self, target: str) -> Mapping[str, Any]:
        agent = self._call(["agent", "get", target]).get("agent")
        if not isinstance(agent, dict):
            raise LauncherError("agent get returned no agent")
        return agent

    def _call(self, arguments: Sequence[str]) -> dict[str, Any]:
        """Run one herdr command and return its `result`, or raise."""
        done = self._run(["herdr", *arguments])
        text = done.stdout if done.returncode == 0 else (done.stderr or done.stdout)
        try:
            body = json.loads(text)
        except json.JSONDecodeError as error:
            raise LauncherError(
                f"herdr {' '.join(arguments[:2])} gave a reply that is not JSON"
            ) from error
        if not isinstance(body, dict):
            raise LauncherError(
                f"herdr {' '.join(arguments[:2])} gave a non-object reply"
            )
        failure = body.get("error")
        if done.returncode != 0 or failure is not None:
            code = failure.get("code") if isinstance(failure, dict) else None
            message = failure.get("message") if isinstance(failure, dict) else ""
            raise LauncherError(
                f"herdr {' '.join(arguments[:2])} failed: {code}: {message}",
                code=code if isinstance(code, str) else None,
            )
        result = body.get("result")
        if not isinstance(result, dict):
            raise LauncherError(f"herdr {' '.join(arguments[:2])} gave no result")
        return result


def _default_table() -> Callable[[], Mapping[int, int]]:
    return read_process_table


def _status_of(agent: Mapping[str, Any]) -> str:
    status = agent.get("agent_status")
    return status if isinstance(status, str) else ""


def _pane_of(agent: Mapping[str, Any]) -> str:
    pane_id = agent.get("pane_id")
    if not isinstance(pane_id, str) or not pane_id:
        raise LauncherError("agent get returned no pane_id")
    return pane_id


def _descendants(table: Mapping[int, int], roots: set[int]) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, parent in table.items():
        children.setdefault(parent, []).append(pid)
    found: set[int] = set()
    queue = list(roots)
    while queue:
        for child in children.get(queue.pop(), []):
            if child not in found and child not in roots:
                found.add(child)
                queue.append(child)
    return found
