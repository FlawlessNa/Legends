"""
The movement playground (`toolkit/movement_playground.py`), offline.

What is checked here is what can be without a client: where a click or a random
draw puts the target, that every way a target or the playground ends releases
every key (the Engine side's release request, with a stand-in pipe, and Main
Process's `release_all` call, with a stand-in for it), that nothing is sent
before a command, that the Action it ships is the production one, and that a
window that goes away, however it goes, quits and stops the Session.

What is not: that the window draws and its clicks land where they point, that
the focus switch behaves when the window is clicked mid-run, and that the
character reaches its targets. Those need the client (the ticket's live run).
"""

import asyncio
import queue
import random
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from pytest_mock import MockerFixture

from botting import controller
from botting.core import ActionRequest, Providers, WindowProvider
from botting.core.bot_data import BotData
from botting.core.errors import DecisionMakerCrashed
from botting.core.supervisor import Supervisor, resolve_pauses
from botting.screen import Reading
from botting.stop_file import STOP_FILENAME
from maple.actions import priorities
from maple.calibration.driver import TrialDriver
from maple.calibration.records import CycleRecord, ListSink, TrialOutcome
from maple.calibration.specs import TrialSchedule
from maple.decision_makers.providers import (
    FRAME,
    ClientProvider,
    MapProvider,
    ProfileProvider,
    ScreenReadersProvider,
)
from maple.model.navigation import FootholdGraph
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.fixture_maps import FIXTURES
from tests.test_maple.serving import serve_skills
from toolkit import movement_playground as mp

# --- choosing targets ---------------------------------------------------------------

#: Five platforms, and from the floor (0 to 100 at y 0) only the floor is
#: reachable without teleport: the others are 110 px up or across a 140 px pit.
SHAFT = WorldMap.from_map_data(FIXTURES["teleport_shaft"]())
SHAFT_GRAPH = FootholdGraph.build(SHAFT, corpus.LAB_PHYSICS, teleport=False)
ON_FLOOR = (50.0, 0.0)


def _floor_reach() -> tuple[Platform, ...]:
    return mp.reachable_platforms(SHAFT_GRAPH, ON_FLOOR)


def test_only_the_floor_is_reachable_from_it() -> None:
    """The premise of the checks below, on the graph the bot plans with."""
    (floor,) = _floor_reach()
    assert (floor.left, floor.right) == (0, 100)
    assert len(SHAFT.platforms) == 5


def test_a_click_near_a_reachable_platform_snaps_onto_it() -> None:
    choice = mp.snap_target((40.0, -6.0), _floor_reach(), SHAFT.platforms)

    assert choice.target == (40, 0)
    assert choice.note == "target (40, 0)"


def test_a_click_off_every_platform_is_snapped_and_says_so() -> None:
    choice = mp.snap_target((50.0, 300.0), _floor_reach(), SHAFT.platforms)

    assert choice.target == (50, 0)
    assert "off every platform" in choice.note


def test_a_click_on_an_unreachable_platform_snaps_to_a_reachable_one() -> None:
    """The click is on the platform across the pit: the target is the nearest
    point the character can reach, the floor's right end, and it says so."""
    choice = mp.snap_target((290.0, 0.0), _floor_reach(), SHAFT.platforms)

    assert choice.target == (100, 0)
    assert "unreachable" in choice.note


def test_a_click_with_nothing_reachable_sets_no_target() -> None:
    choice = mp.snap_target((50.0, 0.0), (), SHAFT.platforms)

    assert choice.target is None


def test_random_targets_land_only_on_reachable_platforms() -> None:
    """Drawn from the whole map, four in five would land off the floor."""
    rng = random.Random(7)
    reach = _floor_reach()
    for _ in range(200):
        choice = mp.random_target(SHAFT, reach, ON_FLOOR, rng)
        assert choice.target is not None
        x, y = choice.target
        assert 0 <= x <= 100
        assert y == 0


def test_a_random_target_is_drawn_away_from_the_character() -> None:
    """On a 600 px floor, a draw within `away` of the character is drawn again."""
    world_map = WorldMap.from_map_data(FIXTURES["walk_corridor"]())
    graph = FootholdGraph.build(world_map, corpus.LAB_PHYSICS)
    reach = mp.reachable_platforms(graph, (16.0, 0.0))
    rng = random.Random(3)
    for _ in range(50):
        choice = mp.random_target(world_map, reach, (16.0, 0.0), rng)
        assert choice.target is not None
        assert abs(choice.target[0] - 16) >= mp.RANDOM_AWAY - 1


# --- the playground: every end releases -------------------------------------------------


def _read(x: float, y: float) -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(x, y, PositionSource.FUSED), 0.0)


@dataclass
class _Core:
    playground: mp.Playground
    released: list[str]
    sink: ListSink


@pytest.fixture
def core() -> _Core:
    released: list[str] = []
    sink = ListSink()

    def new_driver(schedule: TrialSchedule) -> TrialDriver:
        return TrialDriver(schedule, sink)

    def reachable(position: tuple[float, float] | None) -> tuple[Platform, ...] | str:
        if position is None:
            return "no position read yet"
        return mp.reachable_platforms(SHAFT_GRAPH, position)

    playground = mp.Playground(
        SHAFT,
        new_driver=new_driver,
        reachable=reachable,
        release=released.append,
        series=3,
        rng=random.Random(1),
    )
    return _Core(playground, released, sink)


def _arm(core: _Core, target: tuple[float, float] = (90.0, 0.0)) -> TrialDriver:
    """A position read, a click, and the next read: the target's Trial."""
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.CLICK, target, 0.0)
    driver = playground.start(_read(*ON_FLOOR), 0.1)
    assert driver is not None
    return driver


def test_nothing_starts_and_nothing_is_released_before_a_command(core: _Core) -> None:
    for t in range(5):
        assert core.playground.start(_read(*ON_FLOOR), t) is None

    assert core.released == []
    assert not core.sink


def test_a_target_starts_where_the_character_was_read(core: _Core) -> None:
    """Its Trial's start is the read position, so positioning arrives on the
    Trial's first cycle and the next one is measured."""
    driver = _arm(core)
    assert driver.trial is not None
    assert driver.trial.start == (50, 0)
    assert driver.trial.target == (90, 0)

    verdict = driver.advance(_read(*ON_FLOOR), 0.1)

    assert verdict.dispatch is False
    assert driver.phase == "measuring"


def test_a_target_waits_for_a_read_position(core: _Core) -> None:
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.CLICK, (90.0, 0.0), 0.0)

    assert playground.start(Reading.unsure(0.1, "two characters"), 0.1) is None
    assert playground.pending == (90, 0)
    assert "waiting for a position" in playground.note


def test_an_arrival_releases(core: _Core) -> None:
    driver = _arm(core)
    driver.advance(_read(*ON_FLOOR), 0.1)  # positioning arrives
    verdict = driver.advance(_read(90.0, 0.0), 0.5)
    assert verdict.outcome is not None

    core.playground.finish(verdict.outcome, 0.5)

    assert len(core.released) == 1
    assert core.playground.driver is None
    assert "arrived" in core.playground.results[-1]


def test_a_timeout_with_stuck_events_reads_as_stuck(core: _Core) -> None:
    """The driver's own stuck rule: cycles with no progress count stuck events;
    a target that times out with any is reported stuck."""
    core.playground.budget = 2.0
    driver = _arm(core)
    driver.advance(_read(*ON_FLOOR), 0.1)  # positioning arrives
    outcome = None
    for k in range(40):
        verdict = driver.advance(_read(*ON_FLOOR), 0.2 + 0.05 * k)
        if verdict.outcome is not None:
            outcome = verdict.outcome
            break
    assert outcome is not None
    assert outcome.stuck_events > 0

    core.playground.finish(outcome, 3.0)

    assert core.playground.results[-1].split(": ", 1)[1].startswith("stuck: timed out")
    assert len(core.released) == 1


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (mp.CANCEL, None),
        (mp.QUIT, None),
        (mp.CLICK, (20.0, 0.0)),  # a new target replaces the one in flight
        (mp.RANDOM, None),
    ],
)
def test_every_command_that_ends_a_target_releases_and_abandons_it(
    core: _Core, kind: str, payload: object
) -> None:
    _arm(core)

    core.playground.handle(kind, payload, 1.0)

    assert len(core.released) == 1
    outcomes = [r for r in core.sink if isinstance(r, TrialOutcome)]
    assert [o.result for o in outcomes] == ["abandoned"]


def test_cancelling_a_pending_target_releases(core: _Core) -> None:
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.CLICK, (90.0, 0.0), 0.0)

    playground.handle(mp.CANCEL, None, 0.1)

    assert playground.pending is None
    assert core.released == ["cancelled"]


def test_closing_abandons_the_target_and_releases(core: _Core) -> None:
    _arm(core)

    core.playground.close(1.0)

    assert len(core.released) == 1
    assert [r.result for r in core.sink if isinstance(r, TrialOutcome)] == ["abandoned"]


@pytest.mark.parametrize("ends", ["quit", "close"])
def test_a_way_out_with_nothing_running_still_releases(core: _Core, ends: str) -> None:
    if ends == "quit":
        core.playground.handle(mp.QUIT, None, 1.0)
    else:
        core.playground.close(1.0)

    assert len(core.released) == 1


def test_cancel_with_nothing_running_sends_nothing(core: _Core) -> None:
    """No key was pressed for a target, so there is nothing to release."""
    core.playground.start(_read(*ON_FLOOR), 0.0)

    core.playground.handle(mp.CANCEL, None, 0.1)

    assert core.released == []


def test_after_quit_no_command_is_taken(core: _Core) -> None:
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.QUIT, None, 0.0)

    playground.handle(mp.RANDOM, None, 0.1)

    assert playground.pending is None
    assert playground.quitting


def test_a_series_draws_the_next_target_when_one_ends(core: _Core) -> None:
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.SERIES, None, 0.0)
    assert playground.pending is not None
    assert playground.series_left == 2

    driver = playground.start(_read(*ON_FLOOR), 0.1)
    assert driver is not None
    outcome = driver.abandon(0.5)
    assert outcome is not None
    playground.finish(outcome, 0.5)

    assert playground.pending is not None
    assert playground.series_left == 1


def test_cancel_stops_a_series(core: _Core) -> None:
    playground = core.playground
    playground.start(_read(*ON_FLOOR), 0.0)
    playground.handle(mp.SERIES, None, 0.0)

    playground.handle(mp.CANCEL, None, 0.1)

    assert playground.series_left == 0
    assert playground.pending is None


def test_a_click_before_any_read_sets_nothing(core: _Core) -> None:
    core.playground.handle(mp.CLICK, (90.0, 0.0), 0.0)

    assert core.playground.pending is None
    assert "no position read yet" in core.playground.note
    assert core.released == []


# --- the DecisionMaker ------------------------------------------------------------------

ENTRY = next(e for e in corpus.FIXTURE_MAPS if e.name == "walk_corridor")
START = (16.0, 0.0)
TARGET = (288.0, 0.0)


class _Pipe:
    """Stands in for the Engine's pipe: keeps what was sent."""

    def __init__(self) -> None:
        self.sent: list[ActionRequest] = []

    def send(self, request: ActionRequest) -> None:
        self.sent.append(request)


class _NoMinimap:
    """A minimap reader with no client to read."""

    def read(self, frame: object) -> Reading[object]:
        return Reading.unsure(0.0, "no client")


@dataclass
class _Runner:
    runner: mp.PlaygroundRunner
    positions: list[tuple[float, float]]
    pipe: _Pipe
    link: mp.PlaygroundLink
    sink: ListSink

    def decide(self, times: int = 1) -> None:
        for _ in range(times):
            asyncio.run(self.runner._decide())

    def command(self, kind: str, payload: object = None) -> None:
        self.link.commands.put((kind, payload))

    @property
    def releases(self) -> list[ActionRequest]:
        return [r for r in self.pipe.sent if r.procedure is mp.release_every_key]

    @property
    def movements(self) -> list[ActionRequest]:
        return [r for r in self.pipe.sent if r.procedure is controller.compile_and_send]


@pytest.fixture
def harness(tmp_path: Path) -> _Runner:
    """
    A `PlaygroundRunner` without its Session: its `setup()` asks Main Process for
    a lock, so the runner is built from `_setup` on, over a real `BotData` on a
    Corpus map, with the Bot-level Providers `MapleBot` builds, as the
    `TrialRunner` checks build theirs. Its position reader hands out the
    positions a check queues, as fused reads.
    """
    positions: list[tuple[float, float]] = []
    data = BotData("Lab")
    providers = Providers(data, None, None, {})  # pyright: ignore[reportArgumentType] - nothing is sent through them
    providers.add(WindowProvider, handle=corpus.LAB_HANDLE)
    providers.add(
        MapProvider,
        map_id=0,
        world_map=corpus.world_map(ENTRY),
        game_physics=corpus.LAB_PHYSICS_VALUES,
    )
    serve_skills(data, {})
    providers.add(ProfileProvider)
    # What the position is read from; the position itself is stood in for.
    providers.add(ScreenReadersProvider, sprites=None, minimap=_NoMinimap())
    data.provide(FRAME, object.__new__(ClientProvider), lambda: None)
    pipe = _Pipe()
    link = mp.PlaygroundLink(commands=queue.Queue(), view={})
    sink = ListSink()

    self: Any = object.__new__(mp.PlaygroundRunner)
    self.data = data
    self.pipe = pipe
    self.metadata = {"session_dir": str(tmp_path)}
    self.lock = threading.Lock()
    self.correlation_id = "cid-0"
    self._setup(link, sink, tolerance=16.0, budget=60.0, series=2, rng=random.Random(0))

    def virtual() -> Reading[VirtualPosition]:
        x, y = positions.pop(0) if positions else START
        return _read(x, y)

    self._position_reader = virtual
    self.movement_handler.graph(self._physics())
    return _Runner(cast(mp.PlaygroundRunner, self), positions, pipe, link, sink)


async def _supervised(runner: mp.PlaygroundRunner) -> None:
    """Run the runner's decision loop as a Session does: under its Bot's
    Supervisor, until it raises or is cancelled."""
    await Supervisor(
        runner.data.ign, [runner], resolve_pauses([mp.PlaygroundRunner])
    ).run()


def _start_target(h: _Runner) -> None:
    """A read, a click on `TARGET`, the positioning cycle, then a measured one."""
    h.decide()  # a read: the click needs a position to know what is reachable
    h.command(mp.CLICK, TARGET)
    h.decide(2)


def test_idle_cycles_send_nothing_and_publish_the_position(harness: _Runner) -> None:
    harness.decide(5)

    assert harness.pipe.sent == []
    snapshot = harness.link.view["snapshot"]
    assert snapshot["position"] == START
    assert snapshot["running"] is False
    assert snapshot["graph"] == "ready"


def test_a_target_ships_the_production_movement_action(harness: _Runner) -> None:
    """The Action compiles at dispatch (ADR 0002), as `TrialRunner`'s does."""
    _start_target(harness)

    (request,) = harness.movements
    assert request.procedure is controller.compile_and_send
    handle, compiler = request.args
    assert handle == corpus.LAB_HANDLE
    assert "movements" in compiler.keywords
    assert harness.runner.lock.locked()
    snapshot = harness.link.view["snapshot"]
    assert snapshot["target"] == (288, 0)
    assert snapshot["in_flight"] is True
    assert snapshot["route"]
    cycles = [r for r in harness.sink if isinstance(r, CycleRecord)]
    assert [c.phase for c in cycles] == ["positioning", "measuring"]


def test_cancel_releases_every_key_and_cancels_the_action_in_flight(
    harness: _Runner,
) -> None:
    _start_target(harness)

    harness.command(mp.CANCEL)
    harness.decide()

    (release,) = harness.releases
    assert release.cancel_tasks == [f"{harness.runner}"]
    assert release.priority == priorities.FAILSAFE
    assert release.args == (corpus.LAB_HANDLE, "Lab")
    assert [r.result for r in harness.sink if isinstance(r, TrialOutcome)] == [
        "abandoned"
    ]


def test_an_arrival_releases_every_key(harness: _Runner) -> None:
    harness.decide()
    harness.command(mp.CLICK, TARGET)
    harness.positions.extend([START, TARGET])

    harness.decide(2)  # positioning, then a cycle read at the target

    assert harness.movements == []
    assert len(harness.releases) == 1
    assert "arrived" in harness.link.view["snapshot"]["results"][-1]
    assert not harness.runner.lock.locked()


def test_quit_releases_and_asks_the_session_to_stop(
    harness: _Runner, tmp_path: Path
) -> None:
    _start_target(harness)
    sent = len(harness.pipe.sent)

    harness.command(mp.QUIT, "q")
    harness.decide(3)

    assert len(harness.releases) == 1
    assert len(harness.pipe.sent) == sent + 1  # the release, and nothing after it
    assert (tmp_path / STOP_FILENAME).read_text(encoding="utf-8").endswith("q")


def test_an_exception_releases_every_key_on_the_way_out(harness: _Runner) -> None:
    def broken() -> Reading[VirtualPosition]:
        raise RuntimeError("a reader broke")

    _start_target(harness)
    harness.runner._position_reader = broken  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage] - the stand-in's seam

    with pytest.raises(ExceptionGroup) as raised:
        asyncio.run(_supervised(harness.runner))
    assert raised.group_contains(DecisionMakerCrashed, match="a reader broke")

    assert len(harness.releases) == 1
    assert harness.link.view["ended"]
    assert [r.result for r in harness.sink if isinstance(r, TrialOutcome)] == [
        "abandoned"
    ]


def test_a_cancelled_task_releases_every_key(harness: _Runner) -> None:
    """A Session stopping cancels the DecisionMaker's task."""
    _start_target(harness)

    async def run() -> None:
        task = asyncio.create_task(_supervised(harness.runner))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())

    assert len(harness.releases) == 1


# --- the release, in Main Process: the client in front first --------------------------

BINDS = {"jump": "alt_right", "Teleport": "c", "Heal": "space"}


@dataclass
class _Sender:
    """Stands in for the focus switch and the input sender: what was called,
    in order, and with what."""

    calls: list[tuple[str, object]]

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _fake_sender(
    mocker: MockerFixture,
    *,
    held: frozenset[str] = frozenset(),
    swept: frozenset[str] = frozenset({"left", "right", "up", "down"}),
    takes_lock: bool = False,
) -> _Sender:
    sender = _Sender([])

    async def activate(handle: int) -> bool:
        sender.calls.append(("activate", handle))
        if takes_lock:
            await mp.SharedResources.focus_lock.acquire()
        return takes_lock

    def release_keys(keys: list[str], handle: int) -> None:
        sender.calls.append(("release_keys", keys))

    def release_all(handle: int) -> None:
        sender.calls.append(("release_all", handle))

    def clear(handle: int) -> None:
        sender.calls.append(("clear", handle))

    mocker.patch.object(mp, "activate", activate)
    mocker.patch.object(controller, "key_binds", return_value=BINDS)
    mocker.patch.object(mp.HeldKeysLedger, "keys_held", return_value=held)
    mocker.patch.object(mp.HeldKeysLedger, "sweep_candidates", return_value=swept)
    mocker.patch.object(mp.HeldKeysLedger, "clear", side_effect=clear)
    mocker.patch.object(controller, "release_keys", side_effect=release_keys)
    mocker.patch.object(controller, "release_all", side_effect=release_all)
    return sender


def test_the_release_brings_the_client_to_the_front_before_any_key_up(
    mocker: MockerFixture,
) -> None:
    """Key-ups go to the window in front, which is the playground's when a
    command typed there ended the target: the client is activated first."""
    sender = _fake_sender(mocker, held=frozenset({"left"}))

    asyncio.run(mp.release_every_key(4242, "Lab"))

    assert sender.names() == ["activate", "release_keys", "release_all"]
    assert sender.calls[0] == ("activate", 4242)
    assert sender.calls[2] == ("release_all", 4242)


def test_the_release_sends_every_movement_key_up_whatever_the_ledger_says(
    mocker: MockerFixture,
) -> None:
    """A cancelled Action released its keys to the window that was in front,
    and the ledger counts them released: every key a plan presses goes up."""
    sender = _fake_sender(mocker, held=frozenset({"x"}))

    asyncio.run(mp.release_every_key(4242, "Lab"))

    released = dict(sender.calls)["release_keys"]
    assert released == sorted({"left", "right", "up", "down", "alt_right", "c", "x"})


def test_the_sweep_is_skipped_when_it_could_read_the_playground_keys(
    mocker: MockerFixture,
) -> None:
    """Were Escape among the keys the sweep reads, the maintainer's own Esc
    would be taken for a key the bot holds: the ledger is cleared instead."""
    sender = _fake_sender(mocker, swept=frozenset({"left", "escape"}))

    asyncio.run(mp.release_every_key(4242, "Lab"))

    assert sender.names() == ["activate", "release_keys", "clear"]


def test_the_release_gives_back_the_focus_lock_activate_took(
    mocker: MockerFixture,
) -> None:
    sender = _fake_sender(mocker, takes_lock=True)
    mocker.patch.object(controller, "release_keys", side_effect=OSError("gone"))

    with pytest.raises(OSError, match="gone"):
        asyncio.run(mp.release_every_key(4242, "Lab"))

    assert sender.names() == ["activate"]
    assert not mp.SharedResources.focus_lock.locked()


def _end_by(h: _Runner, how: str) -> None:
    """Drive the runner to one way a target, or the playground, ends."""
    if how == "arrival":
        h.decide()
        h.command(mp.CLICK, TARGET)
        h.positions.extend([START, TARGET])
        h.decide(2)
        return
    _start_target(h)
    if how in (mp.CANCEL, mp.QUIT):
        h.command(how)
        h.decide()
    elif how == "replace":
        h.command(mp.CLICK, (100.0, 0.0))
        h.decide()
    elif how == "exception":

        def broken() -> Reading[VirtualPosition]:
            raise RuntimeError("a reader broke")

        h.runner._position_reader = broken  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage] - the stand-in's seam
        with pytest.raises(ExceptionGroup) as raised:
            asyncio.run(_supervised(h.runner))
        assert raised.group_contains(DecisionMakerCrashed, match="a reader broke")
    elif how == "cancelled task":

        async def run() -> None:
            task = asyncio.create_task(_supervised(h.runner))
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(run())


@pytest.mark.parametrize(
    "how",
    ["arrival", mp.CANCEL, "replace", mp.QUIT, "exception", "cancelled task"],
)
def test_every_way_out_activates_the_client_before_releasing(
    harness: _Runner, mocker: MockerFixture, how: str
) -> None:
    """Each release request the runner sends, run as Main Process runs it,
    with the focus switch and the input sender faked."""
    _end_by(harness, how)
    requests = harness.releases
    assert requests

    for request in requests:
        sender = _fake_sender(mocker)
        asyncio.run(request.procedure(*request.args))
        assert sender.names()[:2] == ["activate", "release_keys"]
        assert sender.calls[0] == ("activate", corpus.LAB_HANDLE)


# --- the minimap check at start: nothing pressed ---------------------------------------


@pytest.mark.parametrize(
    ("expanded", "banner", "shown", "starts"),
    [
        (True, False, False, True),
        (True, True, True, True),
        (True, True, False, True),  # map: auto falls back to the canvas
        (False, False, False, False),
        (False, True, False, False),
    ],
)
def test_the_minimap_is_checked_never_pressed(
    mocker: MockerFixture, expanded: bool, banner: bool, shown: bool, starts: bool
) -> None:
    """As `MapleBot._show_minimap`, banner first for `map: auto`, then any
    expanded look; a minimap that isn't expanded refuses the start. Nothing
    here can press a key: only the two reads are stood in for."""
    read = mp.MinimapState.EXPANDED if expanded else mp.MinimapState.ABSENT
    states = mocker.patch.object(mp, "minimap_state", return_value=read)
    banners = mocker.patch.object(mp, "minimap_banner_shown", return_value=shown)
    mocker.patch.object(mp.map_check, "WINDOW", 0.0)
    bot: Any = type("Bot", (), {"data": type("Data", (), {"handle": 7})()})()
    minimap: Any = object()

    if starts:
        mp.PlaygroundBot._show_minimap(bot, minimap, banner=banner)
    else:
        with pytest.raises(mp.StartupRefused):
            mp.PlaygroundBot._show_minimap(bot, minimap, banner=banner)

    assert states.called
    assert banners.called == (banner and expanded)


# --- the window and Main Process ----------------------------------------------------------


def _link() -> mp.PlaygroundLink:
    return mp.PlaygroundLink(commands=queue.Queue(), view={})


def _drain(link: mp.PlaygroundLink) -> list[tuple[str, object]]:
    found = []
    while True:
        try:
            found.append(link.commands.get_nowait())
        except queue.Empty:
            return found


@pytest.mark.parametrize("ends", ["returns", "raises"])
def test_the_window_quits_however_it_ends(mocker: MockerFixture, ends: str) -> None:
    """`q` and the window closed return from `run`; an exception raises. Both
    send `QUIT`."""

    def run(self: mp.Window) -> None:
        if ends == "raises":
            raise RuntimeError("drawing failed")

    mocker.patch.object(mp.Window, "run", run)
    mocker.patch.object(mp.cv2, "destroyAllWindows")
    link = _link()

    mp.run_window(link)

    assert [kind for kind, _ in _drain(link)] == [mp.QUIT]


def test_a_gone_window_quits_and_stops_the_session(tmp_path: Path) -> None:
    link = _link()
    alive = iter([True, True, False])

    asyncio.run(mp.watch_window(lambda: next(alive), link, tmp_path, interval=0.0))

    assert [kind for kind, _ in _drain(link)] == [mp.QUIT]
    assert (tmp_path / STOP_FILENAME).exists()


def test_the_window_in_front_cancels_only_after_the_grace() -> None:
    guard = mp.FrontGuard(grace=0.25)
    running = {"running": True, "in_flight": True}

    assert not guard.update(front=True, now=0.0, **running)
    assert not guard.update(front=True, now=0.2, **running)
    assert guard.update(front=True, now=0.3, **running)


def test_the_window_in_front_cancels_nothing_without_an_action_in_flight() -> None:
    """A click that starts a target leaves this window in front until the
    bot's first Action brings the client back."""
    guard = mp.FrontGuard(grace=0.25)

    for t in range(10):
        assert not guard.update(front=True, running=True, in_flight=False, now=t)


def test_the_window_leaving_the_front_resets_the_grace() -> None:
    guard = mp.FrontGuard(grace=0.25)
    running = {"running": True, "in_flight": True}

    guard.update(front=True, now=0.0, **running)
    guard.update(front=False, now=0.2, **running)
    assert not guard.update(front=True, now=0.3, **running)


def test_the_window_keys() -> None:
    assert mp.key_command(ord("q")) == mp.QUIT
    assert mp.key_command(ord("r")) == mp.RANDOM
    assert mp.key_command(ord("n")) == mp.SERIES
    assert mp.key_command(27) == mp.CANCEL
    assert mp.key_command(ord("x")) is None
    assert mp.key_command(-1) is None


def test_a_playground_key_bound_to_jump_or_teleport_is_a_clash() -> None:
    assert mp.colliding_keys({"jump": "alt_right", "Teleport": "c", "Heal": "r"}) == []
    assert mp.colliding_keys({"jump": "r", "Teleport": "Q"}) == ["q", "r"]
    assert mp.colliding_keys({"jump": "escape"}) == ["escape"]


def test_the_profile_is_the_named_one_or_the_only_own_one() -> None:
    assert mp.pick_profile("mine", ["example", "a", "b"]) == "mine"
    assert mp.pick_profile(None, ["example", "solo"]) == "solo"
    with pytest.raises(mp.ProfileError, match="--profile"):
        mp.pick_profile(None, ["example", "a", "b"])


def test_a_click_in_the_window_is_the_virtual_point_under_it() -> None:
    view = mp.MapView(SHAFT, height=400)
    b = SHAFT.bounds

    assert view.to_view((b.left, b.top)) == (0, 0)
    x, y = view.to_view((50.0, 0.0))
    vx, vy = view.to_virtual(x, y)
    assert abs(vx - 50.0) <= 1 / view.scale
    assert abs(vy - 0.0) <= 1 / view.scale
