"""
Root pytest configuration: fixtures shared by the whole suite.

Nothing here touches a game client. `held_movement_keys` lets offline tests build
an Input Sequence without a Held-Keys Ledger to read from, and `force_overhead`
runs them at a send-loop `OVERHEAD` of their choosing.
"""

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

import botting.controller as controller_package

if TYPE_CHECKING:
    from tests.frame_set import FrameSet

# `botting.controller.inputs` re-exports the `focused_inputs` *function*, shadowing
# the submodule of the same name, so the module object has to be fetched explicitly.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)
inputs_helpers_module = importlib.import_module(
    "botting.controller.inputs.inputs_helpers"
)


@pytest.fixture
def force_overhead(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """
    Sets the send loop's `OVERHEAD` for one test, everywhere it is read.

    `OVERHEAD` is measured once at import: about 1 ms on a quiet machine, 10 ms
    or more when other processes are running. A test whose expectation holds only
    at a small one fails under load (#471, #589); running it at forced values
    makes the load a parameter rather than an accident.

    Three bindings, because each module reads its own: `inputs_helpers` (the
    source, which `_typematic_delay` reads at every `yield`), `focused_inputs`
    (`KeyboardInputWrapper.duration`, `holds`, `fill`, `truncate`), and the
    `botting.controller` re-export the movement builders read as
    `controller.OVERHEAD`. A test that times Steps itself reads
    `controller.OVERHEAD` at call time, not a name imported at collection.

    :return: A setter taking the `OVERHEAD` to use, in seconds.
    """

    def _force(value: float) -> None:
        for module in (
            inputs_helpers_module,
            focused_inputs_module,
            controller_package,
        ):
            monkeypatch.setattr(module, "OVERHEAD", value)

    return _force


@pytest.fixture(
    params=[None, 0.0, 0.012, 0.03], ids=["measured", "0ms", "12ms", "30ms"]
)
def overhead(
    request: pytest.FixtureRequest, force_overhead: Callable[[float], None]
) -> float:
    """
    Runs the test at several send-loop `OVERHEAD`s (`force_overhead`): the one
    measured, none, the 12 ms #473 measured under load, and 30 ms, past
    anything measured so far.

    :return: The `OVERHEAD` the test runs at, in seconds.
    """
    if request.param is not None:
        force_overhead(request.param)
    return controller_package.OVERHEAD


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
