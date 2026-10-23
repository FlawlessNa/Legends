"""
What the loop knows of a worker: a spec to start one, a handle to watch it, and
no way to hand it a credential.

The loop (#159) asks a `Launcher` to start a worker, watch it, read its Claude
session id and stop it, and decides from the answers. Which program actually
starts the worker is behind the protocol: `launchers.herdr` is the only real
implementation, `launchers.fake` is what tests use.

Two rules live here rather than in an implementation, so that no launcher can
drift from them:

- A worker holds no credentials (ruling R11). `worker_spec` is the one function
  the loop builds a `WorkerSpec` with, and it always adds the eight variables
  `stripped_credentials` returns. `check_credentials` is what every `start`
  runs first, so a spec built by hand cannot reach a worker either.
- A name herdr would refuse is refused here, when the spec is built, not at the
  first herdr command.

Credential stripping guards against error, not intent (design section 4, rule
6): it keeps a worker from calling GitHub or pushing by mistake.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Protocol

#: herdr's own rule for an agent name.
NAME_PATTERN: Final = re.compile(r"[a-z][a-z0-9_-]{0,31}")

#: The one role whose spec may carry a session to resume.
RESUMABLE_ROLE: Final = "designer"

#: Non-empty on purpose. With `GH_TOKEN` empty, gh 2.98 still reads the
#: maintainer's token from the OS keyring. A non-empty value wins over the
#: keyring and over `GITHUB_TOKEN`, GitHub rejects it, and `gh auth login`
#: refuses while it is set.
NO_CREDENTIALS_SENTINEL: Final = "factory-worker-has-no-credentials"

#: Where the empty gh config directory lives, under the git common dir.
GH_CONFIG_SUBPATH: Final = Path("factory") / "gh-config-empty"

CREDENTIAL_VARIABLES: Final[tuple[str, ...]] = (
    "GH_TOKEN",
    "GH_CONFIG_DIR",
    "GITHUB_TOKEN",
    "GIT_ASKPASS",
    "GIT_TERMINAL_PROMPT",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
)


class WorkerState(enum.Enum):
    WORKING = "working"
    FINISHED = "finished"
    BLOCKED = "blocked"
    GONE = "gone"


@dataclass(frozen=True)
class Handle:
    """
    A started worker, by the pane it lives in rather than by its name.

    A name follows whichever agent holds it; the pane id is what the loop
    created. `prompt_started` is False for a worker found by a replayed `start`
    and for one whose prompt was never seen to begin, so an idle reading is not
    mistaken for a finished turn.
    """

    name: str
    pane_id: str
    role: str
    prompt_started: bool


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    cwd: Path
    env: Mapping[str, str]
    model: str
    prompt: str
    resume: str | None

    def __post_init__(self) -> None:
        if not NAME_PATTERN.fullmatch(self.name):
            raise ValueError(
                f"worker name {self.name!r} does not match herdr's "
                f"{NAME_PATTERN.pattern}"
            )
        if self.resume is not None and self.env.get("FACTORY_ROLE") != RESUMABLE_ROLE:
            raise ValueError(
                f"resume is only for the {RESUMABLE_ROLE} role, "
                f"not {self.env.get('FACTORY_ROLE')!r}"
            )
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


class LauncherError(Exception):
    """
    A launcher could not do what it was asked, and says so rather than guess.

    `handle` is set when a worker had already been created: the loop stops it.
    `code` is herdr's error code, when the error came from herdr.
    """

    def __init__(
        self, message: str, *, handle: Handle | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.handle = handle
        self.code = code


class Launcher(Protocol):
    def start(self, spec: WorkerSpec) -> Handle:
        """Start a worker. Idempotent by name."""
        ...

    def status(self, handle: Handle) -> WorkerState: ...

    def session_id(self, handle: Handle) -> str | None: ...

    def stop(self, handle: Handle) -> None:
        """Return only once the worker's processes are gone."""
        ...


def stripped_credentials(common_dir: Path) -> dict[str, str]:
    """
    The eight variables that leave a worker with nothing to authenticate with.

    Creates the empty `GH_CONFIG_DIR` when absent. Raises when it exists and
    holds anything: a worker that wrote gh config there would otherwise hand it
    to every later worker.
    """
    config_dir = common_dir / GH_CONFIG_SUBPATH
    if config_dir.exists():
        if not config_dir.is_dir() or any(config_dir.iterdir()):
            raise LauncherError(
                f"GH_CONFIG_DIR {config_dir} exists and is not an empty directory"
            )
    else:
        config_dir.mkdir(parents=True)
    return {
        "GH_TOKEN": NO_CREDENTIALS_SENTINEL,
        "GH_CONFIG_DIR": str(config_dir),
        "GITHUB_TOKEN": "",
        "GIT_ASKPASS": "",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
    }


def worker_spec(
    *,
    role: str,
    stage: str,
    ticket: int,
    name: str,
    cwd: Path,
    model: str,
    prompt: str,
    common_dir: Path,
    resume: str | None = None,
) -> WorkerSpec:
    """The one way the loop builds a spec: role variables plus no credentials."""
    env = {
        "FACTORY_ROLE": role,
        "FACTORY_STAGE": stage,
        "FACTORY_TICKET": str(ticket),
        **stripped_credentials(common_dir),
    }
    return WorkerSpec(
        name=name, cwd=cwd, env=env, model=model, prompt=prompt, resume=resume
    )


def check_credentials(spec: WorkerSpec, common_dir: Path) -> None:
    """Raise, naming the variable, unless `spec` carries all eight as expected."""
    expected = stripped_credentials(common_dir)
    for variable in CREDENTIAL_VARIABLES:
        if variable not in spec.env:
            raise LauncherError(f"worker {spec.name!r} lacks {variable}")
        if spec.env[variable] != expected[variable]:
            raise LauncherError(
                f"worker {spec.name!r} carries {variable} with a value other than "
                "the stripped one"
            )
