"""
`HUNTING_AREA`, `AREA_STRETCHES` and `AREA_PRESENCE` (#578), on the Fixture map
of `test_hunting_area` with a minimap transform whose canvas px is 16 virtual px.

No game client and no window: the minimap reader is a stand-in, the launch
window's function is replaced by one that records what it is given, and the
saved areas are written under a temporary folder. Presence is decided by
`PresenceCounter` on a fake clock, sampled once a second.
"""

import importlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from botting.core import BotData, DecisionMaker, StartupRefused
from botting.screen import Reading
from botting.utilities import Box
from maple.decision_makers.providers import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    HUNTING_AREA,
    MapProvider,
    OtherPlayers,
)
from maple.decision_makers.providers import hunting_area as module
from maple.decision_makers.providers.hunting_area import (
    LEAVE_AFTER,
    NEAR,
    NOBODY,
    OTHERS_MEMORY,
    SAMPLE_CAP,
    SETTLE_PRESENCE,
    SETTLE_WINDOW,
    AreaPresence,
    HuntingAreaProvider,
    PresenceCounter,
)
from maple.launchers import hunting_area_window
from maple.launchers.hunting_area_window import LiveReading, NoDisplay
from maple.model.world import HuntingArea, MinimapTransform, Platform, WorldMap
from maple.model.world.hunting_area import save_area
from maple.screen.minimap import MinimapState, MinimapView
from maple.telemetry_events import ROTATION_AREA_SET
from tests.test_maple.serving import Served, assemble, serve
from tests.test_maple.test_hunting_area import fixture_map, platform

WORLD = replace(fixture_map(), minimap=MinimapTransform((500, 1500), 4))
#: The flat Platform at y 0, from x 0 to 1000, and the one at y -1000 above it.
FLAT = platform(WORLD, 1)
HIGH = platform(WORLD, 20)
#: Holds the part of `FLAT` from 200 to 600.
AREA = HuntingArea(200, -100, 600, 50)
#: Holds the whole of `FLAT` and of `HIGH`.
BOTH = HuntingArea(0, -1100, 1000, 50, "both")
#: Holds no Platform.
EMPTY = HuntingArea(1200, -100, 1500, 50, "empty")
#: The canvas px of a marker drawn at virtual (508, 4), inside `AREA`.
INSIDE_MARKER = (63, 94)
HANDLE = 7
#: The pathing module: the package exports a function of that name.
PATHING = importlib.import_module("maple.decision_makers.providers.pathing")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Frame:
    """What the client shows: a frame read in front."""

    ok = True


class Reader:
    """A minimap reader that shows one `another` marker, and records the markers
    each read asks for. Its canvas is a stand-in."""

    canvas = object()

    def __init__(self, markers: tuple[tuple[int, int], ...] = (INSIDE_MARKER,)) -> None:
        self.markers = markers
        self.asked: list[tuple[str, ...]] = []

    def read(self, frame: object, markers: Iterable[str] = ()) -> Reading[MinimapView]:
        kinds = tuple(markers)
        self.asked.append(kinds)
        view = MinimapView(
            state=MinimapState.EXPANDED,
            map_area=Box(left=10, right=90, top=30, bottom=90),
            bounds=Box(left=0, right=100, top=0, bottom=100),
            self_position=Reading.read((40, 60), 1.0),
            markers={"another": self.markers} if "another" in kinds else {},
            shown=Box(left=0, right=80, top=37, bottom=97),
        )
        return Reading.read(view, 1.0)


class Window:
    """The launch window's function: records each call, and gives `answer`."""

    def __init__(self, answer: HuntingArea | None | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> HuntingArea | None:  # noqa: ANN401 - recorded as given
        self.calls.append(args)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The saved areas' folder, with `AREA` saved as `corner` and `EMPTY`."""
    save_area(WORLD, replace(AREA, name="corner"), tmp_path)
    save_area(WORLD, EMPTY, tmp_path)
    save_area(WORLD, BOTH, tmp_path)
    monkeypatch.setattr(HuntingAreaProvider, "FOLDER", tmp_path)
    return tmp_path


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    records: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        HuntingAreaProvider,
        "emit",
        lambda self, event_type, payload=None: records.append((event_type, payload)),
    )
    return records


def built(
    monkeypatch: pytest.MonkeyPatch,
    window: Window | None = None,
    *,
    reader: Reader | None = None,
    clock: Clock | None = None,
    world: WorldMap = WORLD,
    **settings: object,
) -> Served:
    """The Provider, built and set up as assembly builds it, with the profile
    `settings`; the launch window is `window`'s, or one that fails the test."""
    opened = window or Window(AssertionError("the launch window opened"))
    monkeypatch.setattr(hunting_area_window, "choose_hunting_area", opened)
    served = serve(
        monkeypatch,
        data=BotData("Bot", clock=clock or Clock()),
        frames=Frame,
        handle=HANDLE,
        minimap=reader or Reader(),
    )
    served.providers.add(MapProvider, map_id=world.id, world_map=world)
    served.providers.settings.update(settings)
    assemble(served, _Reads)
    return served


class _Reads(DecisionMaker):
    """What reads the three keys, so that assembly builds their Provider."""

    reads = (HUNTING_AREA, AREA_STRETCHES, AREA_PRESENCE)


def reachable(
    monkeypatch: pytest.MonkeyPatch, platforms: tuple[Platform, ...] | None
) -> None:
    """The Platforms a Path reaches from the character, as pathing answers."""
    monkeypatch.setattr(PATHING, "reachable_platforms", lambda _data: platforms)


# --- HUNTING_AREA ----------------------------------------------------------------


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"rotation": "random"},
        {"rotation": "smart", "mob_count_threshold": 2},
        {"smart_rotation_enabled": True},
    ],
    ids=["no rotation", "random", "smart", "smart_rotation_enabled"],
)
def test_another_rotation_gives_none_opening_no_window_and_reading_no_file(
    monkeypatch: pytest.MonkeyPatch,
    emitted: list[tuple[str, Any]],
    settings: dict[str, Any],
) -> None:
    loaded: list[object] = []
    monkeypatch.setattr(module, "load_area", lambda *args: loaded.append(args))
    reader = Reader()

    served = built(monkeypatch, reader=reader, **settings)

    data = served.data
    assert data.read(HUNTING_AREA) is None
    assert data.read(AREA_STRETCHES) is None
    assert data.read(AREA_PRESENCE) is None
    assert loaded == []
    assert reader.asked == []
    assert emitted == []


def test_a_saved_name_is_loaded_and_no_window_opens(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    reader = Reader()

    served = built(
        monkeypatch, reader=reader, rotation="hunting_area", hunting_area="corner"
    )

    # Each key holds its initial value, and building read no frame.
    managed = served.data._managed  # pyright: ignore[reportPrivateUsage] - unread values
    assert managed[HUNTING_AREA.name].value == replace(AREA, name="corner")
    assert managed[AREA_STRETCHES.name].value == AREA.stretches(WORLD)
    assert managed[AREA_PRESENCE.name].value == NOBODY
    assert reader.asked == []


def test_with_no_saved_name_the_window_is_asked_with_what_it_needs(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    window = Window(AREA)
    reader = Reader()

    served = built(monkeypatch, window, reader=reader, rotation="hunting_area")

    assert served.data.read(HUNTING_AREA) == AREA
    ((world, canvas, where, handle, read),) = window.calls
    assert (world, canvas, where, handle) == (WORLD, Reader.canvas, folder, HANDLE)
    # Its live read: the character and the other players, from one fresh read
    # of the minimap with the `another` markers asked for.
    live = read()
    assert isinstance(live, LiveReading)
    assert reader.asked == [("another",)]
    assert live.others == [(508, 4)]
    assert live.character is not None


def test_the_area_is_announced_once(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    served = built(monkeypatch, Window(AREA), rotation="hunting_area")
    for _ in range(3):
        served.data.update_attribute(HUNTING_AREA.name)

    assert emitted == [
        (
            ROTATION_AREA_SET,
            {
                "map_id": WORLD.id,
                "left": 200,
                "top": -100,
                "right": 600,
                "bottom": 50,
                "name": None,
                "origin": "window",
            },
        )
    ]


def test_a_saved_area_is_announced_with_its_name(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    built(monkeypatch, rotation="hunting_area", hunting_area="corner")

    ((event_type, payload),) = emitted
    assert event_type == ROTATION_AREA_SET
    assert (payload["name"], payload["origin"]) == ("corner", "profile")


@pytest.mark.parametrize(
    ("window", "settings"),
    [
        (Window(None), {}),
        (Window(NoDisplay("there is no display")), {}),
        (None, {"hunting_area": "nowhere"}),
        (None, {"hunting_area": "empty"}),
        (Window(EMPTY), {}),
    ],
    ids=["window closed", "no display", "unknown", "empty saved", "empty drawn"],
)
def test_each_way_of_having_no_area_refuses_the_start_naming_the_setting(
    monkeypatch: pytest.MonkeyPatch,
    folder: Path,
    emitted: list[tuple[str, Any]],
    window: Window | None,
    settings: dict[str, Any],
) -> None:
    with pytest.raises(StartupRefused, match="`hunting_area"):
        built(monkeypatch, window, rotation="hunting_area", **settings)

    assert emitted == []


# --- AREA_STRETCHES ----------------------------------------------------------------


def test_every_stretch_until_reachability_is_known(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    reachable(monkeypatch, None)

    served = built(monkeypatch, rotation="hunting_area", hunting_area="both")
    served.data.update_attribute(AREA_STRETCHES.name)

    assert served.data.read(AREA_STRETCHES) == BOTH.stretches(WORLD)
    assert {s.platform for s in BOTH.stretches(WORLD)} == {FLAT, HIGH}


def test_only_the_reachable_stretches_once_reachability_is_known(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    served = built(monkeypatch, rotation="hunting_area", hunting_area="both")
    reachable(monkeypatch, (HIGH,))

    served.data.update_attribute(AREA_STRETCHES.name)

    assert served.data.read(AREA_STRETCHES) == BOTH.stretches(WORLD, among=(HIGH,))


def test_every_stretch_with_one_error_when_none_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
    folder: Path,
    emitted: list[tuple[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    served = built(monkeypatch, rotation="hunting_area", hunting_area="corner")
    reachable(monkeypatch, (HIGH,))

    with caplog.at_level(logging.ERROR):
        for _ in range(3):
            served.data.update_attribute(AREA_STRETCHES.name)

    assert served.data.read(AREA_STRETCHES) == AREA.stretches(WORLD)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


# --- AREA_PRESENCE, through the Provider -----------------------------------------


def test_presence_is_sampled_once_per_read_of_the_other_players(
    monkeypatch: pytest.MonkeyPatch, folder: Path, emitted: list[tuple[str, Any]]
) -> None:
    samples: list[float] = []
    sample = PresenceCounter.sample

    def counted(self: PresenceCounter, *args: Any) -> AreaPresence:  # noqa: ANN401 - passed on
        samples.append(self.clock())
        return sample(self, *args)

    monkeypatch.setattr(PresenceCounter, "sample", counted)
    clock = Clock()
    served = built(
        monkeypatch, clock=clock, rotation="hunting_area", hunting_area="corner"
    )

    for now in (0.0, 1.5):
        clock.now = now
        # Refreshed twice on one read of the other players: one sample.
        served.data.update_attribute(AREA_PRESENCE.name)
        served.data.update_attribute(AREA_PRESENCE.name)

    assert samples == [0.0, 1.5]
    presence = served.data.read(AREA_PRESENCE)
    assert presence is not None
    assert presence.inside == 1


# --- PresenceCounter -----------------------------------------------------------------

#: Inside `AREA`; within `NEAR` of it; farther.
IN = (400.0, 0.0)
BESIDE = (800.0, 0.0)
FAR = (1200.0, 0.0)
STRETCHES = AREA.stretches(WORLD)


def players(*positions: tuple[float, float]) -> Reading[OtherPlayers]:
    return Reading.read(OtherPlayers(positions, None), 0.0)


UNSURE: Reading[OtherPlayers] = Reading.unsure(0.0, "minimap not found")


def run(
    counter: PresenceCounter,
    clock: Clock,
    seconds: Iterable[int],
    read: Callable[[int], Reading[OtherPlayers]],
) -> dict[int, AreaPresence]:
    """Sample once a second, at each of `seconds`; the presence after each."""
    found = {}
    for second in seconds:
        clock.now = float(second)
        found[second] = counter.sample(read(second), STRETCHES)
    return found


def counter() -> tuple[PresenceCounter, Clock]:
    clock = Clock()
    return PresenceCounter(AREA, clock), clock


def test_the_constants_start_where_the_spec_says() -> None:
    assert (NEAR, SETTLE_WINDOW, SETTLE_PRESENCE) == (350, 60, 30)
    assert (LEAVE_AFTER, SAMPLE_CAP, OTHERS_MEMORY) == (60, 2, 5)


def test_settled_starts_at_30_s_inside_of_the_last_60() -> None:
    presence, clock = counter()

    found = run(
        presence, clock, range(60), lambda s: players(IN) if s >= 10 else players()
    )

    # Inside from 10 s, each sample standing for the second before it.
    assert not found[38].settled
    assert found[39].settled


def test_one_player_inside_for_20_s_does_not_settle() -> None:
    presence, clock = counter()

    found = run(
        presence,
        clock,
        range(200),
        lambda s: players(IN) if 10 <= s < 30 else players(BESIDE),
    )

    assert not any(p.settled for p in found.values())


def test_settled_ends_60_s_after_the_last_inside_sample() -> None:
    presence, clock = counter()

    found = run(
        presence, clock, range(200), lambda s: players(IN) if s <= 50 else players()
    )

    assert found[50].settled
    assert found[109].settled
    assert not found[110].settled
    assert not any(found[s].settled for s in range(110, 200))


def test_an_unsure_read_changes_nothing() -> None:
    sure, sure_clock = counter()
    mixed, mixed_clock = counter()

    def inside(second: int) -> Reading[OtherPlayers]:
        return players(IN) if 10 <= second <= 50 else players()

    expected = run(sure, sure_clock, range(150), inside)
    for second in range(150):
        mixed_clock.now = second
        assert mixed.sample(inside(second), STRETCHES) == expected[second]
        before = mixed.value
        mixed_clock.now = second + 0.5
        assert mixed.sample(UNSURE, STRETCHES) == before


def test_a_long_gap_counts_for_the_cap_and_the_first_sample_for_nothing() -> None:
    presence, clock = counter()

    # The first at 0 s stands for nothing, the one at 30 s for 2 s, then one
    # second each: 30 s from 2 + 28, at 58 s.
    found = run(presence, clock, [0, *range(30, 60)], lambda s: players(IN))

    assert SAMPLE_CAP == 2
    assert not found[30].settled
    assert not found[57].settled
    assert found[58].settled


def test_others_are_the_players_in_or_near_the_area_of_the_last_5_s() -> None:
    presence, clock = counter()

    found = run(
        presence,
        clock,
        range(8),
        lambda s: players(IN, BESIDE, FAR) if s == 0 else players(),
    )

    # A read that misses them keeps them, until 5 s have passed.
    assert set(found[0].others) == {IN, BESIDE}
    assert set(found[4].others) == {IN, BESIDE}
    assert found[5].others == ()


def test_free_share_is_1_before_anyone_has_settled() -> None:
    presence, clock = counter()

    found = run(presence, clock, range(20), lambda s: players(IN, BESIDE))

    assert all(p.free_share == 1.0 for p in found.values())
    assert set(found[19].others) == {IN, BESIDE}


def test_free_share_is_0_when_every_cell_is_near_another_player() -> None:
    presence, clock = counter()

    found = run(presence, clock, range(40), lambda s: players(IN))

    # Every cell of 200 to 600 has its middle within 350 of x 400.
    assert found[39].settled
    assert found[39].free_share == 0.0


def test_free_share_counts_the_cells_far_from_every_other_player() -> None:
    clock = Clock()
    presence = PresenceCounter(BOTH, clock)
    flat = BOTH.stretches(WORLD, among=(FLAT,))

    last = presence.value
    for second in range(40):
        clock.now = second
        last = presence.sample(players((100.0, 0.0)), flat)

    # x 0 to 1000 is 7 cells, their middles 71, 214, 357, 500, 643, 786 and
    # 929: the first three are within 350 of x 100.
    assert last.settled
    assert last.free_share == pytest.approx(4 / 7)
