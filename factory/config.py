"""
`configs/factory.toml`: the caps the maintainer owns (#218).

Read from the **session's** checkout, like the model table, so a ticket branch
cannot raise its own caps (the principle of #216). v1 routing never reads it.

A wrong file is a `ConfigError`, which is exit 3: the maintainer's file is
wrong and a re-run will not fix it. Nothing here guesses a default, because a
typo'd cap that silently falls back is a cap nobody set. The one command that
reads the file is #159's, and it maps the error to that exit code.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final

from factory.exit_codes import ExitCode

#: Relative to the repo root, beside the model table.
CONFIG_PATH: Final = Path("configs") / "factory.toml"

_CAPS: Final = ("attempts", "cycles", "wip")
_OPTIONAL: Final = ("worker_timeout_min", "poll_s")
_KNOWN: Final = (*_CAPS, "launcher", *_OPTIONAL)


class ConfigError(Exception):
    """The config is wrong, and only the maintainer can settle it."""

    exit_code: ClassVar[ExitCode] = ExitCode.NEEDS_HUMAN


@dataclass(frozen=True)
class Config:
    """A validated `factory.toml`."""

    attempts: int
    cycles: int
    wip: int
    launcher: str
    #: Optional until the ticket that reads them supplies their values (#159).
    worker_timeout_min: int | None = None
    poll_s: float | None = None


def _positive_int(raw: dict[str, Any], key: str) -> int:
    value = raw[key]
    # `bool` is an `int` in Python, so `attempts = true` would pass without this.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{key} must be a positive integer, got {value!r}.")
    return value


def _positive_number(raw: dict[str, Any], key: str) -> float:
    value = raw[key]
    ok = isinstance(value, int | float) and not isinstance(value, bool)
    if not ok or value <= 0:
        raise ConfigError(f"{key} must be a positive number, got {value!r}.")
    return value


def load(path: Path) -> Config:
    """Read and fully validate the file, or raise `ConfigError` naming the key."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as missing:
        raise ConfigError(f"no config at {path}: {missing}") from missing
    except tomllib.TOMLDecodeError as broken:
        raise ConfigError(f"{path} is not valid TOML: {broken}") from broken

    unknown = sorted(set(raw) - set(_KNOWN))
    if unknown:
        raise ConfigError(
            f"{path}: unknown key {unknown[0]!r}. The keys are {sorted(_KNOWN)}."
        )
    for key in (*_CAPS, "launcher"):
        if key not in raw:
            raise ConfigError(f"{path}: {key} is required.")

    launcher = raw["launcher"]
    if not isinstance(launcher, str) or not launcher.strip():
        raise ConfigError(f"launcher must be a non-empty string, got {launcher!r}.")

    timeout = (
        _positive_int(raw, "worker_timeout_min")
        if "worker_timeout_min" in raw
        else None
    )
    poll = _positive_number(raw, "poll_s") if "poll_s" in raw else None
    return Config(
        attempts=_positive_int(raw, "attempts"),
        cycles=_positive_int(raw, "cycles"),
        wip=_positive_int(raw, "wip"),
        launcher=launcher,
        worker_timeout_min=timeout,
        poll_s=poll,
    )


def read(session: Path) -> Config:
    """The config of the session's own checkout."""
    return load(session / CONFIG_PATH)
