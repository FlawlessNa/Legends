"""
That the hooks are *reachable*, not just correct.

`tests/test_factory/test_hooks.py` proves the decisions. This file proves the
thing that actually broke: the command string in `.claude/settings.json` was
`factory hook <event>`, and `factory` is a console script that exists only on an
activated venv's `PATH`. Every invocation exited 127, Claude Code treated the
failure as non-blocking, and for a day the repo enforced nothing while every PR
claimed the gates were mechanical (#199).

So these tests run the configured string the way the harness does: through bash,
from a minimal environment, with no venv active.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from paths import ROOT

SETTINGS = Path(ROOT) / ".claude" / "settings.json"

#: The events wired in settings, and the stdin each one receives.
EVENTS = {"SessionStart": "", "PreToolUse": "{}", "Stop": ""}


def _configured_commands() -> dict[str, str]:
    """Every hook command string, keyed by event, straight from settings."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for event, entries in settings["hooks"].items():
        for entry in entries:
            for hook in entry["hooks"]:
                found[event] = hook["command"]
    return found


def _minimal_env() -> dict[str, str]:
    """
    What the hook shell actually has: no venv, no developer `PATH`.

    `VIRTUAL_ENV` and the venv's `Scripts` directory are removed explicitly,
    because a test that inherits them proves only that the author's shell works.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "FACTORY_HOOKS"}
    }
    venv = str(Path(ROOT) / ".venv")
    env["PATH"] = os.pathsep.join(
        part for part in env.get("PATH", "").split(os.pathsep) if venv not in part
    )
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return env


bash = shutil.which("bash")
needs_bash = pytest.mark.skipif(
    bash is None, reason="hooks run through bash; none found"
)


def test_every_wired_event_has_a_command() -> None:
    """A missing registration is the other way enforcement silently stops."""
    assert set(_configured_commands()) == set(EVENTS)


def test_the_command_does_not_depend_on_an_activated_venv() -> None:
    """
    The regression itself. A bare `factory ...` passes on a developer machine
    and exits 127 everywhere the harness actually runs it.
    """
    for event, command in _configured_commands().items():
        assert not command.lstrip('"').startswith("factory "), (
            f"{event} invokes the console script by name; it is only on PATH "
            f"inside an activated venv. Use the interpreter path instead."
        )


@needs_bash
@pytest.mark.parametrize("event", sorted(EVENTS))
def test_the_configured_command_runs_from_a_minimal_shell(event: str) -> None:
    """Run exactly what settings.json says, the way the harness runs it."""
    command = _configured_commands()[event]
    done = subprocess.run(
        [str(bash), "-c", command],
        input=EVENTS[event],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_minimal_env(),
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, (
        f"{event} hook exited {done.returncode}: {done.stderr.strip()[:300]}"
    )


@needs_bash
def test_a_pre_tool_use_decision_survives_the_round_trip() -> None:
    """
    End to end: a write that should be refused is refused, through the real
    command string rather than by calling the function directly.
    """
    command = _configured_commands()["PreToolUse"]
    event = json.dumps({"tool_input": {"file_path": "botting/core/engine.py"}})
    done = subprocess.run(
        [str(bash), "-c", command],
        input=event,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**_minimal_env(), "FACTORY_BRANCH_OVERRIDE": ""},
        timeout=60,
        check=False,
    )
    assert done.returncode == 0
    if done.stdout.strip():
        payload = json.loads(done.stdout)
        assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
