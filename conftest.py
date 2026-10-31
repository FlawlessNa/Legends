"""
Root pytest configuration: fixtures shared by the whole suite.

Nothing here touches a game client. The one fixture below exists so that offline
tests can build an Input Sequence without a Held-Keys Ledger to read from.
"""

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.frame_set import FrameSet

# `botting.controller.inputs` re-exports the `focused_inputs` *function*, shadowing
# the submodule of the same name, so the module object has to be fetched explicitly.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)


@pytest.fixture
def held_movement_keys(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """
    Pins what `KeyboardInputWrapper.__post_init__` sees as already held.

    Construction normally reads the Held-Keys Ledger, which only Main Process owns
    and which carries state across tests; patching the lookup makes the
    opposite-key releases inserted at construction a function of the test alone.

    Starts out with nothing held. Call the fixture to change that::

        def test_something(held_movement_keys):
            held_movement_keys("left")
            wrapper = KeyboardInputWrapper(handle, ["right"], ["keydown"])

    :return: A setter taking the movement keys to report as held.
    """
    held: list[str] = []

    def _get_held_movement_keys(hwnd: int) -> list[str]:
        return list(held)

    monkeypatch.setattr(
        focused_inputs_module, "get_held_movement_keys", _get_held_movement_keys
    )

    def _set_held(*keys: str) -> None:
        held[:] = keys

    return _set_held


@pytest.fixture(scope="session")
def frames() -> FrameSet:
    """
    The current tag's real frames, with their expected readings.

    Skips, saying which command fetches them, when they aren't on disk. Tests
    using it carry `@pytest.mark.frames`.
    """
    # Imported here so the default run doesn't load OpenCV for a fixture it skips.
    from tests import frame_set

    try:
        return frame_set.open_frame_set(frame_set.current_tag())
    except frame_set.FrameSetMissing as exc:
        pytest.skip(str(exc))
