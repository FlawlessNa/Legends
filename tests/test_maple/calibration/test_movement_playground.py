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
from typing import Any, ClassVar, cast

import pytest
from pytest_mock import MockerFixture

from botting import controller
from botting.core import ActionRequest
from botting.core.bot_data import BotData
from botting.screen import Reading
from botting.stop_file import STOP_FILENAME
from maple.actions import priorities
from maple.calibration.driver import TrialDriver
from maple.calibration.records import CycleRecord, ListSink, TrialOutcome
from maple.calibration.specs import TrialSchedule
from maple.model.navigation import FootholdGraph
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.fixture_maps import FIXTURES
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


class _Character:
    skills: ClassVar[dict[str, object]] = {}


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
    A `PlaygroundRunner` without its Session: `__init__` asks Main Process for
    a lock and the decision gates, so the runner is built from `_setup` on, over
    a real `BotData` on a Corpus map, as the `TrialRunner` checks build theirs.
    `current_position` hands out the positions a check queues, as fused reads.
    """
    positions: list[tuple[float, float]] = []
    data = BotData("Lab")
    data.set_static("handle", corpus.LAB_HANDLE)
    data.set_static("world_map", corpus.world_map(ENTRY))
    data.set_static("game_physics", corpus.LAB_PHYSICS_VALUES)
    data.set_static("speed_multiplier", 1.0)
    data.set_static("jump_multiplier", 1.0)
    data.set_static("character", _Character())
    # What the minimap attributes are made from; the position is stood in for.
    data.set_static("current_frame", None)
    data.set_static("minimap_reader", _NoMinimap())
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

    data.create_or_reconfigure_attribute("current_position", virtual)
    data.movement_handler.graph(self._physics())
    data.reconfigure_attribute("path", threshold=1e-9)
    return _Runner(cast(mp.PlaygroundRunner, self), positions, pipe, link, sink)


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
    assert release.args == (corpus.LAB_HANDLE,)
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
    harness.runner.data.reconfigure_attribute("current_position", broken)

    async def run() -> None:
        await harness.runner.task()

    with pytest.raises(RuntimeError, match="a reader broke"):
        asyncio.run(run())

    assert len(harness.releases) == 1
    assert harness.link.view["ended"]
    assert [r.result for r in harness.sink if isinstance(r, TrialOutcome)] == [
        "abandoned"
    ]


def test_a_cancelled_task_releases_every_key(harness: _Runner) -> None:
    """A Session stopping cancels the DecisionMaker's task."""
    _start_target(harness)

    async def run() -> None:
        task = asyncio.create_task(harness.runner.task())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())

    assert len(harness.releases) == 1


def test_the_release_procedure_is_release_all_on_the_client(
    mocker: MockerFixture,
) -> None:
    """In Main Process, the release request runs `controller.release_all` on
    the client's handle: the fake stands in for the input sender."""
    release_all = mocker.patch.object(controller, "release_all")

    asyncio.run(mp.release_every_key(4242))

    release_all.assert_called_once_with(4242)


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
