"""
The minimap's consumers on the new reader, fed synthetic frames: the map check,
`MinimapProvider` and the position it reads, and the state
`ensure_minimap_displayed` waits for.

The Bot-level Providers are built as `MapleBot.child_init` builds them, with the
synthetic minimap's reader, and a client that shows whatever frame the test
puts on it.
"""

import asyncio
import random
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture, MockType

from botting.core import ActionRequest, BotData, Key, Providers, WindowProvider
from botting.core.supervisor import resolve_pauses
from botting.logging_config import bucket_for
from botting.screen import Frame, Reading, Status, capture
from game_data.sprites import Sprite
from maple.actions import menus
from maple.decision_makers import (
    CheckMobsStillSpawn,
    MobsHitting,
    Rotation,
)
from maple.decision_makers.ensure_still_in_map import CheckStillInMap, map_title
from maple.decision_makers.mixins import MinimapAttributesMixin
from maple.decision_makers.providers import (
    FRAME,
    HANDLE,
    MINIMAP_BOX,
    MINIMAP_READING,
    MINIMAP_SHOWN,
    POSITION,
    ClientProvider,
    MapProvider,
    MinimapProvider,
    MinimapRecovery,
    PositionReader,
    ScreenReadersProvider,
)
from maple.decision_makers.providers import minimap as minimap_provider
from maple.decision_makers.providers.minimap import UNPLACED_LIMIT, minimap_position
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState, MinimapView
from maple.screen.position import Fusion, PositionSource, VirtualPosition
from maple.telemetry_events import (
    POSITION_READ,
    RECOVERY_MAP_CHECK_FAILED,
    RECOVERY_MAP_CHECK_RECOVERED,
)
from tests.test_maple.test_screen_minimap import (
    CANVAS,
    MAP_ID,
    OTHER_CANVAS,
    draw_minimap,
    draw_minimised,
    frame,
    occlude,
    reader,
    screen,
    sprites,
)


def _minimap(
    canvas: Sprite | None = CANVAS, user_at: tuple[int, int] | None = (30, 30)
) -> Frame:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=canvas, user_at=user_at)
    return frame(pixels)


def _minimised() -> Frame:
    pixels = screen()
    draw_minimised(pixels, 30, 10)
    return frame(pixels)


class _Client:
    """The client's capture: it shows `shown`, which a test changes."""

    def __init__(self, shown: Frame) -> None:
        self.shown = shown

    def grab(self, handle: int) -> Frame:
        return self.shown


class _Proxies:
    """Main Process's proxies, made here: a Condition is a thread's."""

    def instance(self, key: str, primitive_type: str) -> object:
        return getattr(threading, primitive_type)()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _Client:
    shown = _Client(_minimap())
    monkeypatch.setattr(capture, "_source", shown)
    return shown


@pytest.fixture
def pipe(mocker: MockerFixture) -> MockType:
    return mocker.Mock()


def _serving(
    pipe: MockType,
    map_id: int | None = MAP_ID,
    fusion: object = None,
) -> BotData:
    """
    A Bot's data with its Bot-level Providers: the window, the minimap's reader
    (for `map_id`, None for a map the bot doesn't know), the map, and the
    client's frame.
    """
    data = BotData("Tester")
    providers = Providers(data, pipe, _Proxies(), {})  # pyright: ignore[reportArgumentType] - a stand-in
    providers.add(WindowProvider, handle=1)
    providers.add(ScreenReadersProvider, sprites=sprites(), minimap=reader(map_id))
    providers.add(
        MapProvider,
        map_id=MAP_ID,
        world_map=(
            None
            if map_id is None
            else SimpleNamespace(id=map_id, name=None, street=None)
        ),
        position_fusion=fusion,
    )
    providers.add(ClientProvider, chat_keys={})
    return data


# --- CheckStillInMap ----------------------------------------------------------


def _check(
    client: _Client, pipe: MockType, shown: Frame, map_id: int | None
) -> CheckStillInMap:
    client.shown = shown
    check = CheckStillInMap({}, _serving(pipe, map_id), pipe)  # pyright: ignore[reportArgumentType] - no Manager needed
    check.setup()
    return check


def test_with_a_map_id_the_check_passes_on_the_maps_own_minimap(
    client: _Client, pipe: MockType
) -> None:
    assert _check(client, pipe, _minimap(CANVAS), MAP_ID)._perform_check()


def test_with_a_map_id_the_check_fails_on_another_maps_minimap(
    client: _Client, pipe: MockType
) -> None:
    assert not _check(client, pipe, _minimap(OTHER_CANVAS), MAP_ID)._perform_check()


def test_without_a_map_id_the_check_only_asks_that_the_minimap_is_shown(
    client: _Client, pipe: MockType
) -> None:
    assert _check(client, pipe, _minimap(OTHER_CANVAS), None)._perform_check()
    assert not _check(client, pipe, frame(screen()), None)._perform_check()


@pytest.mark.parametrize("map_id", [MAP_ID, None])
def test_a_minimised_minimap_fails_the_check(
    client: _Client, pipe: MockType, map_id: int | None
) -> None:
    assert not _check(client, pipe, _minimised(), map_id)._perform_check()


def test_the_check_names_the_map_as_the_client_does() -> None:
    """The map comes from `WorldMap` (#398), so its name does too."""
    world = SimpleNamespace(id=10002000, name="Ellinia", street="Victoria Road")

    assert map_title(world) == "Victoria Road: Ellinia"  # pyright: ignore[reportArgumentType]
    assert map_title(SimpleNamespace(id=7, name=None, street=None)) == "7"  # pyright: ignore[reportArgumentType]
    assert map_title(None) == "an unknown map"


def test_a_covered_minimap_fails_the_check(client: _Client, pipe: MockType) -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=CANVAS)
    occlude(pixels, 250, 20, 6, 72)

    assert not _check(client, pipe, frame(pixels), MAP_ID)._perform_check()
    assert not _check(client, pipe, frame(pixels), None)._perform_check()


def test_each_check_looks_at_a_fresh_frame(client: _Client, pipe: MockType) -> None:
    """Not one served from the frame's 0.1 s cache: the map may just have changed."""
    check = _check(client, pipe, _minimap(CANVAS), MAP_ID)
    assert check._perform_check()

    client.shown = _minimap(OTHER_CANVAS)
    assert not check._perform_check()


def test_off_the_map_after_recovering_it_stops_the_same_classes_until_resume(
    client: _Client, pipe: MockType, mocker: MockerFixture
) -> None:
    """
    The classes the legacy `_disable_decision_makers` named, itself included,
    now paused by the user's Pause, which only Discord `RESUME` releases, and one
    advanced reaction in the chat.
    """
    check = _check(client, pipe, _minimap(OTHER_CANVAS), MAP_ID)
    recovered = mocker.patch.object(check, "_recovery")
    paused = mocker.patch.object(check, "pause_for_user")
    reacted = mocker.patch.object(check._reactions, "react")

    asyncio.run(check._decide())

    recovered.assert_called_once_with()
    paused.assert_called_once_with(
        Rotation,
        CheckStillInMap,
        CheckMobsStillSpawn,
        MobsHitting,
        reason=f"not on {MAP_ID}",
    )
    reacted.assert_called_once_with("advanced")


def test_back_on_the_map_after_recovering_it_pauses_nothing(
    client: _Client, pipe: MockType, mocker: MockerFixture
) -> None:
    check = _check(client, pipe, _minimap(OTHER_CANVAS), MAP_ID)

    def recover() -> None:
        client.shown = _minimap(CANVAS)

    mocker.patch.object(check, "_recovery", side_effect=recover)
    paused = mocker.patch.object(check, "pause_for_user")
    emitted = mocker.patch.object(check, "emit")

    asyncio.run(check._decide())

    paused.assert_not_called()
    assert [call.args[0] for call in emitted.call_args_list] == [
        RECOVERY_MAP_CHECK_FAILED,
        RECOVERY_MAP_CHECK_RECOVERED,
    ]


def test_the_classes_it_pauses_are_declared() -> None:
    """`pause_for_user` raises on a class `pauses` does not name."""
    assert resolve_pauses([CheckStillInMap])[CheckStillInMap] == {
        Rotation,
        CheckStillInMap,
        CheckMobsStillSpawn,
        MobsHitting,
    }


def test_it_has_no_mixin_and_declares_what_its_helpers_read() -> None:
    assert not [c for c in CheckStillInMap.__mro__ if c.__name__.endswith("Mixin")]
    from maple.decision_makers.reactions import Reactions

    for key in (*MinimapRecovery.reads, *Reactions.reads):
        assert key in CheckStillInMap.reads


# --- The minimap's data -------------------------------------------------------


def test_the_minimaps_logs_stay_in_the_movement_bucket() -> None:
    """The recovery's and the position's lines, which `_map_mixins` logged."""
    assert bucket_for(minimap_provider.logger.name) == "movement"


def test_every_minimap_consumer_declares_the_minimap_reader() -> None:
    assert MINIMAP in MinimapAttributesMixin.screen_readers
    assert MINIMAP in CheckStillInMap.screen_readers


@pytest.fixture
def ensured(mocker: MockerFixture) -> MockType:
    """`ensure_minimap_displayed`, at the Provider: it presses nothing."""
    return mocker.patch.object(minimap_provider, "ensure_minimap_displayed")


def _provided(pipe: MockType, fusion: object = None) -> BotData:
    data = _serving(pipe, fusion=fusion)
    data.build_provider(MinimapProvider)
    return data


def test_setup_shows_the_minimap_then_registers_its_keys_in_order(
    client: _Client, pipe: MockType, ensured: MockType, mocker: MockerFixture
) -> None:
    """The I/O `_create_minimap_attributes` did, in its order: the minimap
    shown, then the reading, whether shown and the box read at once, and the
    position left for its first reader."""
    data = _serving(pipe)
    order: list[str] = []
    ensured.side_effect = lambda *_: order.append("shown")
    provide = BotData.provide

    def registered(data: BotData, key: Key[Any], *rest: Any, **kw: Any) -> None:  # noqa: ANN401
        order.append(key.name)
        provide(data, key, *rest, **kw)

    mocker.patch.object(BotData, "provide", autospec=True, side_effect=registered)

    data.build_provider(MinimapProvider)

    assert order == [
        "shown",
        "minimap_reading",
        "minimap_shown",
        "minimap_box",
        "position",
    ]
    identifier, handle, ign, sent_through, minimap, _, limit = ensured.call_args.args
    assert identifier == "MinimapProvider(Tester) Initial Setup"
    assert (handle, ign, sent_through, limit) == (1, "Tester", pipe, 7.5)
    assert isinstance(minimap, MinimapReader)


def test_the_minimap_is_set_up_once_however_many_ask(
    client: _Client, pipe: MockType, ensured: MockType
) -> None:
    """
    `_create_minimap_attributes` asks `BotData` to build `MinimapProvider` if it
    is not built yet: the minimap is shown once at start, and its keys keep
    their first configuration, however many unported DecisionMakers ask.
    """
    data = _serving(pipe)

    class _Asking(MinimapAttributesMixin):
        def __init__(self) -> None:
            self.data = data

    for _ in range(3):
        _Asking()._create_minimap_attributes()

    ensured.assert_called_once()
    assert [type(p) for p in data.providers or ()].count(MinimapProvider) == 1
    assert data.minimap_reading.status is Status.READ


@pytest.mark.parametrize(
    ("shown", "displayed"),
    [
        (_minimap(), True),
        (_minimised(), False),
        (frame(screen()), False),
    ],
)
def test_the_minimap_counts_as_displayed_only_when_expanded(
    client: _Client, pipe: MockType, ensured: MockType, shown: Frame, displayed: bool
) -> None:
    """The Stuck detector's guard (`_on_expected_minimap`) reads this: a
    minimised minimap shows no map."""
    client.shown = shown

    assert _provided(pipe).minimap_currently_displayed is displayed


def _shown_now(data: BotData, client: _Client, shown: Frame) -> None:
    client.shown = shown
    for key in (FRAME, MINIMAP_READING, MINIMAP_SHOWN, MINIMAP_BOX):
        data.refresh(key)


def test_a_covered_minimap_keeps_the_last_answers_and_absent_says_not_shown(
    client: _Client, pipe: MockType, ensured: MockType
) -> None:
    """No policy for a covered minimap yet: whether it is shown, and where,
    keep their last values (`HeldReading`). Not on screen is an answer."""
    data = _provided(pipe)
    bounds = data.read(MINIMAP_BOX)
    assert data.read(MINIMAP_SHOWN) is True
    assert bounds is not None

    covered = _minimap()
    occlude(covered.pixels, 250, 20, 6, 72)
    _shown_now(data, client, covered)
    assert data.read(MINIMAP_READING).status is Status.COVERED
    assert data.read(MINIMAP_SHOWN) is True
    assert data.read(MINIMAP_BOX) == bounds

    _shown_now(data, client, frame(screen()))
    assert data.read(MINIMAP_READING).status is Status.ABSENT
    assert data.read(MINIMAP_SHOWN) is False
    assert data.read(MINIMAP_BOX) == bounds


def test_unported_code_reads_the_minimap_by_its_legacy_names(
    client: _Client, pipe: MockType, ensured: MockType
) -> None:
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    data = _provided(pipe, fusion=_Fusion(fused))

    assert data.current_entire_minimap_box == data.read(MINIMAP_BOX)
    assert data.minimap_currently_displayed is data.read(MINIMAP_SHOWN)
    assert data.current_position == data.read(POSITION) == fused


def test_without_a_map_id_the_position_raises_for_the_error_handler() -> None:
    with pytest.raises(ValueError, match="position unsure: no map_id"):
        minimap_position(reader(map_id=None).read(_minimap()))


def test_the_position_is_the_markers() -> None:
    assert minimap_position(reader().read(_minimap(user_at=(12, 34)))) == (12, 34)


@pytest.mark.parametrize(
    ("shown", "says"),
    [
        (frame(screen()), "minimap absent"),
        (_minimap(user_at=None), "marker isn't found"),
        (_minimised(), "minimised"),
    ],
)
def test_no_position_raises_for_the_error_handler(shown: Frame, says: str) -> None:
    with pytest.raises(ValueError, match=says):
        minimap_position(reader().read(shown))


# --- The state ensure_minimap_displayed waits for -----------------------------


@pytest.mark.parametrize(
    ("pixels", "state"),
    [
        (lambda: _minimap().pixels, MinimapState.EXPANDED),
        (lambda: _minimised().pixels, MinimapState.MINIMISED),
        (screen, MinimapState.ABSENT),
        (lambda: np.zeros((300, 400, 3), np.uint8), None),
    ],
)
def test_the_minimap_state_is_read_off_a_fresh_capture(
    mocker: MockerFixture, pixels: Callable[[], np.ndarray], state: MinimapState | None
) -> None:
    grabbed = frame(pixels())
    source = mocker.Mock()
    source.grab.return_value = grabbed
    mocker.patch.object(menus, "frame_source", return_value=source)
    minimap: MinimapReader = reader()

    assert menus.minimap_state(minimap, 1) is state
    source.grab.assert_called_once_with(1)


def _without_banner() -> Frame:
    pixels = screen()
    draw_minimap(pixels, 250, 20, banner=False)
    return frame(pixels)


@pytest.mark.parametrize(
    ("shown", "banner"),
    [
        (_minimap, True),
        (_without_banner, False),
        (_minimised, False),
        (lambda: frame(screen()), False),
    ],
)
def test_the_banner_is_asked_of_a_fresh_capture(
    mocker: MockerFixture, shown: Callable[[], Frame], banner: bool
) -> None:
    source = mocker.Mock()
    source.grab.return_value = shown()
    mocker.patch.object(menus, "frame_source", return_value=source)

    assert menus.minimap_banner_shown(reader(), 1) is banner


@pytest.mark.parametrize("banner", [True, False])
def test_ensure_minimap_displayed_waits_for_the_banner_only_when_asked(
    mocker: MockerFixture, banner: bool
) -> None:
    """On the look without the banner, the toggle is pressed again only when
    the banner is asked for."""
    source = mocker.Mock()
    source.grab.return_value = _without_banner()
    mocker.patch.object(menus, "frame_source", return_value=source)
    action = mocker.patch.object(menus, "ActionWithValidation")

    menus.ensure_minimap_displayed(
        "test", 1, "Tester", mocker.Mock(), reader(), mocker.Mock(), 1.0, banner=banner
    )

    validator = action.call_args.args[1]
    assert validator() is not banner


# --- Keeping the cursor off the minimap ----------------------------------------


# A client area that starts 8 px right and 31 px down from the window's corner,
# as on a framed window, with the window itself somewhere else on the screen.
_WINDOW_RECT = (100, 50, 516, 389)
_CLIENT_ORIGIN = (108, 81)


class _Holder:
    """Who holds a `MinimapRecovery`: it reads the keys the test sets, and
    records what it sends."""

    def __init__(self, box: object) -> None:
        self.data = SimpleNamespace(ign="Tester")
        self.values: dict[Key[Any], object] = {HANDLE: 1, MINIMAP_BOX: box}
        self.sent: list[ActionRequest] = []

    def read(self, key: Key[Any]) -> object:
        return self.values[key]

    def send(self, request: ActionRequest) -> None:
        self.sent.append(request)


def test_the_cursor_is_moved_off_the_minimap_where_it_is_on_screen(
    mocker: MockerFixture,
) -> None:
    """
    The box avoided and the point chosen are both in client pixels, and
    `controller.mouse_move` places a client point with `ClientToScreen`: so the
    cursor lands off the minimap on screen, whatever the window's border and
    title bar add. Were either in window pixels, some points would land on the
    minimap's bottom or right strip, which a few hundred draws hit.
    """
    from botting.controller import high_level

    mocker.patch.object(
        minimap_provider.win32gui, "GetClientRect", return_value=(0, 0, 400, 300)
    )
    mocker.patch.object(high_level.win32gui, "GetWindowRect", return_value=_WINDOW_RECT)
    mocker.patch.object(
        high_level.win32gui,
        "ClientToScreen",
        side_effect=lambda _, p: (p[0] + _CLIENT_ORIGIN[0], p[1] + _CLIENT_ORIGIN[1]),
    )
    reading = reader().read(_minimap())
    assert reading.value is not None
    bounds = reading.value.bounds
    holder = _Holder(bounds)
    recovery = MinimapRecovery(holder, _Proxies())  # pyright: ignore[reportArgumentType] - a stand-in
    random.seed(311)

    for _ in range(300):
        recovery.move_cursor_off_minimap("test")

    sent = [request.args[1] for request in holder.sent]
    on_screen = [high_level.client_to_screen(1, point) for point in sent]
    ox, oy = _CLIENT_ORIGIN
    assert not [
        (x, y)
        for x, y in on_screen
        if bounds.left + ox <= x < bounds.right + ox
        and bounds.top + oy <= y < bounds.bottom + oy
    ]


def test_the_error_handler_moves_the_cursor_before_it_toggles_the_minimap(
    client: _Client, pipe: MockType, ensured: MockType, mocker: MockerFixture
) -> None:
    client.shown = _minimap(user_at=(12, 34))
    data = _provided(pipe)
    [provider] = [p for p in data.providers or () if isinstance(p, MinimapProvider)]
    recovery = provider._recovery  # pyright: ignore[reportPrivateUsage]
    order: list[str] = []
    mocker.patch.object(minimap_provider.time, "sleep")
    ensured.side_effect = lambda *_: order.append("toggle")
    mocker.patch.object(
        recovery, "move_cursor_off_minimap", side_effect=lambda _: order.append("mouse")
    )

    recovery()

    assert order == ["mouse", "toggle"]


def test_the_error_handler_names_its_actions_after_its_holder(
    client: _Client, pipe: MockType, ensured: MockType, mocker: MockerFixture
) -> None:
    """`CheckStillInMap`'s recovery is its own, as its mixin's call was."""
    mocker.patch.object(minimap_provider.time, "sleep")
    mocker.patch.object(
        minimap_provider.win32gui, "GetClientRect", return_value=(0, 0, 400, 300)
    )
    check = _check(client, pipe, _minimap(user_at=(12, 34)), MAP_ID)
    check.data.build_provider(MinimapProvider)
    check._recovery.proxies = _Proxies()  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage] - a stand-in
    sent = mocker.patch.object(check, "send")

    check._recovery()  # pyright: ignore[reportPrivateUsage]

    [mouse] = [call.args[0] for call in sent.call_args_list]
    assert mouse.identifier == "CheckStillInMap(Tester).current_position Error Handler"
    assert ensured.call_args.args[0] == mouse.identifier


# --- The virtual position (#392) ------------------------------------------------


class _Fusion:
    """
    Answers `position`, and counts its reads. `minimap_read` says whether the
    minimap gave a position, as `Fusion.minimap` does.
    """

    def __init__(
        self, position: Reading[VirtualPosition], *, minimap_read: bool = True
    ) -> None:
        self.position = position
        self.minimap_read = minimap_read
        self.reads = 0

    def read(self, frame: Frame, minimap: Reading[MinimapView]) -> Fusion:
        self.reads += 1
        return Fusion(self.position, (600, 336) if self.minimap_read else None, near=1)


class _Located:
    """A `PositionReader` on a minimap reading, a frame and a fusion the test
    sets, recording what it emits."""

    def __init__(self, fusion: _Fusion | None, shown: Frame | None = None) -> None:
        self.shown = shown or _minimap()
        self.minimap = reader().read(self.shown)
        self.fusion = fusion
        self.emitted: list[tuple[str, Any]] = []
        self.reader = PositionReader(
            "Tester",
            lambda event, payload: self.emitted.append((event, payload)),
            fusion=lambda: self.fusion,  # pyright: ignore[reportArgumentType] - a stand-in
            minimap=lambda: self.minimap,
            frame=lambda: self.shown,
        )

    def __call__(self) -> Reading[VirtualPosition]:
        return self.reader()


def test_the_position_is_fusions_and_each_read_is_recorded() -> None:
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    located = _Located(_Fusion(fused))

    assert located() == fused
    assert located.emitted == [
        (
            POSITION_READ,
            {
                "status": "read",
                "source": "fused",
                "x": 605.5,
                "y": 340.0,
                "minimap_x": 600,
                "minimap_y": 336,
                "camera_x": None,
                "camera_y": None,
                "found": 0,
                "near": 1,
                "by_tag": False,
                "own_elsewhere": False,
                "detail": "",
            },
        )
    ]


def test_an_unsure_fusion_with_the_minimap_read_is_returned_for_its_consumer() -> None:
    """
    A fusion `UNSURE` though the minimap placed the character (`PositionFusion`
    gives none since #529, which makes disagreeing reads and a crowd `coarse`):
    the minimap's error handler can't fix that, so the `UNSURE` reading is the
    answer, and a consumer holds (#396: `MovementsMixin` plans no Path).
    """
    unsure = Reading.unsure(3.0, "the reads disagree")
    located = _Located(_Fusion(unsure))

    assert located() == unsure
    assert [(e, p["status"], p["source"]) for e, p in located.emitted] == [
        (POSITION_READ, "unsure", None)
    ]


def test_an_unsure_position_with_no_minimap_read_raises_for_the_error_handler() -> None:
    """With no minimap position, the minimap's handler is the one to make it readable."""
    located = _Located(
        _Fusion(Reading.unsure(3.0, "minimap unsure: covered"), minimap_read=False)
    )

    with pytest.raises(ValueError, match="position unsure: minimap unsure: covered"):
        located()
    assert [(e, p["status"], p["source"]) for e, p in located.emitted] == [
        (POSITION_READ, "unsure", None)
    ]


class _Clock:
    """`time.monotonic` for the minimap Provider's module, moved by hand."""

    def __init__(self, mocker: MockerFixture) -> None:
        self.now = 1000.0
        mocker.patch.object(minimap_provider.time, "monotonic", side_effect=self.read)

    def read(self) -> float:
        return self.now


def _unplaced() -> tuple[_Located, _Fusion]:
    """The minimap shown, its map found, and no marker on it: the position
    `COVERED`, which fusion turns into an `UNSURE` read with no minimap."""
    unplaced = _Fusion(
        Reading.unsure(3.0, "minimap position covered: marker isn't found"),
        minimap_read=False,
    )
    located = _Located(unplaced, _minimap(user_at=None))
    view = located.minimap.value
    assert view is not None
    assert view.self_position.status is Status.COVERED
    return located, unplaced


def test_an_unplaced_marker_holds_instead_of_raising(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """#502: re-showing the minimap can't place a marker it doesn't draw, so
    the bot holds (`UNSURE`, no Path planned) and says why once."""
    clock = _Clock(mocker)
    located, unplaced = _unplaced()

    with caplog.at_level("WARNING"):
        for _ in range(3):
            assert located() == unplaced.position
            clock.now += 50.0

    holds = [r for r in caplog.records if "holds" in r.getMessage()]
    assert len(holds) == 1
    assert "marker isn't found" in holds[0].getMessage()


def test_an_unplaced_marker_raises_for_the_error_handler_after_the_limit(
    mocker: MockerFixture,
) -> None:
    clock = _Clock(mocker)
    located, _ = _unplaced()
    located()

    clock.now += UNPLACED_LIMIT - 0.1
    located()
    clock.now += 0.1
    with pytest.raises(ValueError, match=f"for {UNPLACED_LIMIT:.0f} s"):
        located()


def test_a_placed_read_starts_the_wait_over(mocker: MockerFixture) -> None:
    clock = _Clock(mocker)
    located, unplaced = _unplaced()
    located()
    clock.now += UNPLACED_LIMIT - 1

    placed = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.COARSE), 3.0)
    located.fusion = _Fusion(placed)
    assert located() == placed
    located.fusion = unplaced
    for _ in range(2):
        clock.now += UNPLACED_LIMIT - 1
        assert located() == unplaced.position
        located.fusion = _Fusion(placed)
        located()
        located.fusion = unplaced


def test_an_unplaced_marker_neither_calls_the_error_handler_nor_fails_the_read(
    client: _Client, pipe: MockType, ensured: MockType, mocker: MockerFixture
) -> None:
    """Through `BotData`, as the rotation reads it: the hold is the value, so
    the handler (5 attempts, then the Engine fails) isn't reached."""
    clock = _Clock(mocker)
    handler = mocker.patch.object(MinimapRecovery, "__call__")
    unplaced = _Fusion(Reading.unsure(3.0, "covered"), minimap_read=False)
    client.shown = _minimap(user_at=None)
    data = _provided(pipe, fusion=unplaced)

    for _ in range(4):
        data.update_attribute("current_position")
        assert data.current_position == unplaced.position
        clock.now += 30.0
    handler.assert_not_called()


@pytest.mark.parametrize(
    ("shown", "says"),
    [
        (lambda: frame(screen()), "minimap absent"),
        (_minimised, "minimised"),
    ],
)
def test_a_minimap_not_shown_still_raises_at_once(
    shown: Callable[[], Frame], says: str
) -> None:
    """The handler can fix these: it shows the minimap."""
    located = _Located(_Fusion(Reading.unsure(3.0, says), minimap_read=False), shown())

    with pytest.raises(ValueError, match=says):
        located()


def test_without_a_fusion_the_position_raises_for_the_error_handler() -> None:
    located = _Located(None)

    with pytest.raises(ValueError, match="no position fusion"):
        located()
    assert located.emitted == []


def test_the_position_has_the_minimaps_error_handler_and_waits_to_be_read(
    client: _Client, pipe: MockType, ensured: MockType
) -> None:
    """Building the Provider reads no position, so it sends nothing: the first
    consumer to ask reads it, and a read the minimap can't place goes to the
    minimap's error handler. `current_minimap_position` is gone from `BotData`
    (#398)."""
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    fusion = _Fusion(fused)

    data = _provided(pipe, fusion=fusion)

    managed = data._managed  # pyright: ignore[reportPrivateUsage] - the attribute's configuration
    assert fusion.reads == 0
    assert isinstance(managed[POSITION.name].error_handler, MinimapRecovery)
    assert "current_minimap_position" not in managed
    assert data.current_position == fused
    assert fusion.reads == 1


def test_a_decision_makers_own_position_reads_are_its_own(
    client: _Client, pipe: MockType, ensured: MockType, mocker: MockerFixture
) -> None:
    """
    `TrialRunner` reads a position for each sample through the mixin's
    `_get_position`: its records carry its decision's Correlation ID, as they
    did, and its hold is its own.
    """
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    fusion = _Fusion(fused)
    data = _provided(pipe, fusion=fusion)
    emitted = mocker.Mock()

    class _Sampling(MinimapAttributesMixin):
        def __init__(self) -> None:
            self.data = data
            self.emit = emitted

    sampling = _Sampling()

    assert sampling._get_position() == fused  # pyright: ignore[reportPrivateUsage]
    [(event, _)] = [call.args for call in emitted.call_args_list]
    assert event == POSITION_READ
    assert fusion.reads == 1
