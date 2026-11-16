"""Input is refused when Windows would silently drop it (UIPI), with Win32 stubbed."""

import pytest

from botting.utilities import elevation
from botting.utilities.elevation import Elevation, input_blocked_reason

OWN, TARGET = 1, 2


def _tokens(
    monkeypatch: pytest.MonkeyPatch, own: bool | None, target: bool | None
) -> None:
    monkeypatch.setattr(
        elevation, "_token_elevated", lambda pid: {OWN: own, TARGET: target}[pid]
    )


@pytest.mark.parametrize(
    ("own", "target", "refused"),
    [
        (True, True, False),
        (False, False, False),
        (True, False, False),
        (False, True, True),
        (False, None, True),
        (True, None, True),
    ],
)
def test_input_is_refused_only_when_it_would_be_dropped(
    monkeypatch: pytest.MonkeyPatch, own: bool, target: bool | None, refused: bool
) -> None:
    _tokens(monkeypatch, own, target)

    reason = input_blocked_reason(TARGET, own_pid=OWN)

    assert (reason is not None) is refused


def test_an_unreadable_token_is_reported_as_higher_integrity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tokens(monkeypatch, False, None)

    assert "higher integrity" in (input_blocked_reason(TARGET, own_pid=OWN) or "")
    assert elevation.process_elevation(TARGET) is Elevation.UNREADABLE
