"""
Telemetry Event Types are additive only (`maple/AGENTS.md`): an offline analyzer
is written against them, so one is never removed, renamed or repurposed.

`tests/telemetry_event_types.json` lists every Event Type constant there is,
by name and value, per module. The current constants must contain all of it: a
new Event Type passes without touching the file, a removed or renamed one fails.
Add a new one to the file when you add it, so it is protected from then on.

This catches a removal and a rename of a name or a value. It cannot see an Event
Type whose payload changed meaning: that stays the reviewer's to check.
"""

import importlib
import json
import re
from pathlib import Path

import pytest

GOLDEN = Path(__file__).with_name("telemetry_event_types.json")
MODULES = ("botting.telemetry_events", "maple.telemetry_events")
EVENT_TYPE = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")


def current(module_name: str) -> dict[str, str]:
    """The module's Event Type constants: public names holding `area.event`."""
    module = importlib.import_module(module_name)
    return {
        name: value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str) and EVENT_TYPE.fullmatch(value)
    }


def golden() -> dict[str, dict[str, str]]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_the_golden_list_covers_the_modules_that_hold_event_types() -> None:
    assert set(golden()) == set(MODULES)


@pytest.mark.parametrize("module_name", MODULES)
def test_no_event_type_was_removed_or_renamed(module_name: str) -> None:
    now = current(module_name)
    gone = {
        name: value
        for name, value in golden()[module_name].items()
        if now.get(name) != value
    }

    assert not gone, (
        f"{module_name} lost or changed these Event Types, which are additive "
        f"only (maple/AGENTS.md): {gone}"
    )
