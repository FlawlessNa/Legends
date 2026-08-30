"""
Provenance checks over the Event Type constant modules.

An Event Type is the key an offline analyzer groups a Session's Telemetry
Records on, so its *shape* is the contract - dotted ``<area>.<event>`` in
``snake_case``. Nothing validates that at runtime, and deliberately so:
`emit_event` may never raise inside a Producer. This is where the convention is
enforced instead.

There is no test hunting call sites for string literals. That would check
provenance rather than correctness, and it is the kind of test that gets
suppressed the first time it is inconvenient.
"""

import re
from typing import Final, get_type_hints

import pytest

from botting import telemetry_events as engine_events
from maple import telemetry_events as game_events

#: Dotted `<area>.<event>`, both halves `snake_case`, neither starting with a
#: digit or an underscore.
EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

MODULES = (engine_events, game_events)


def _constants(module) -> dict[str, str]:
    """
    :param module: An Event Type constants module.
    :return: Every ``Final`` string it declares, by name.
    """
    hints = get_type_hints(module, include_extras=False)
    return {
        name: getattr(module, name)
        for name, hint in hints.items()
        if hint is Final and isinstance(getattr(module, name, None), str)
    }


def _all_constants() -> list[tuple[str, str]]:
    return [
        (f"{module.__name__}.{name}", value)
        for module in MODULES
        for name, value in _constants(module).items()
    ]


@pytest.mark.parametrize("name, value", _all_constants())
def test_event_type_matches_the_dotted_convention(name, value):
    assert EVENT_TYPE_RE.match(value), f"{name} = {value!r} is not <area>.<event>"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_module_declares_event_types(module):
    """
    Guards the parametrisation above: a scan that silently found nothing would
    make every shape assertion vacuous.
    """
    assert _constants(module)


def test_event_types_are_unique_across_modules():
    """
    The two modules split by layer, not by namespace, and both feed one stream.
    A value declared twice would make the analyzer's grouping key ambiguous.
    """
    values = [value for _, value in _all_constants()]
    assert len(values) == len(set(values))
