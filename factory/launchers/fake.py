"""
A launcher that starts nothing, for tests of the loop and the dry run.

It keeps the rules every launcher shares: the credential check before anything
is recorded, idempotent start, and no stopping a designer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from factory.launcher import (
    RESUMABLE_ROLE,
    Handle,
    LauncherError,
    WorkerSpec,
    WorkerState,
    check_credentials,
)


class FakeLauncher:
    def __init__(
        self,
        common_dir: Path,
        *,
        states: Mapping[str, Sequence[WorkerState]] | None = None,
        session_ids: Mapping[str, str | None] | None = None,
    ) -> None:
        self._common_dir = common_dir.resolve()
        self._script = {name: list(seq) for name, seq in (states or {}).items()}
        self._calls: dict[str, int] = {}
        self._session_ids = dict(session_ids or {})
        self._handles: dict[str, Handle] = {}
        self._gone: set[str] = set()
        self.started: list[WorkerSpec] = []
        self.stopped: list[Handle] = []

    def start(self, spec: WorkerSpec) -> Handle:
        check_credentials(spec, self._common_dir)
        if spec.name in self._handles:
            return self._handles[spec.name]
        handle = Handle(
            spec.name,
            f"fake:{spec.name}",
            spec.env.get("FACTORY_ROLE", ""),
            True,
        )
        self.started.append(spec)
        self._handles[spec.name] = handle
        return handle

    def status(self, handle: Handle) -> WorkerState:
        if handle.pane_id in self._gone:
            return WorkerState.GONE
        sequence = self._script.get(handle.name)
        if not sequence:
            raise LauncherError(f"no scripted states for {handle.name!r}")
        index = self._calls.get(handle.name, 0)
        self._calls[handle.name] = index + 1
        return sequence[min(index, len(sequence) - 1)]

    def session_id(self, handle: Handle) -> str | None:
        return self._session_ids.get(handle.name)

    def stop(self, handle: Handle) -> None:
        if handle.role == RESUMABLE_ROLE:
            raise LauncherError(f"never stop a designer ({handle.name!r})")
        self.stopped.append(handle)
        self._gone.add(handle.pane_id)
