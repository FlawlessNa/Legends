"""
Movement playground (#524): send the character to picked targets; it sends input.

You pick targets on the map and watch how the bot's own movement stack gets the
character there.

    python -m toolkit.movement_playground --map "Victoria Road: Ellinia"
    python -m toolkit.movement_playground --profile nass --map auto --budget 90

A window shows the map the character is on (its static render, darkened, with
the foothold graph's platforms and ropes drawn lightly), the character's
position read live, and the target. Pick a target; the bot plans a Path to it
on the foothold graph, compiles it into Movement Plans, and sends the keys, as
a Session does. When the target ends (arrived, timed out, stuck, cancelled),
pick the next one. It replaces the old `movements_calibration.py`.

**The window may take the focus when it opens**, as any new window does.
Nothing is sent before a target, and the first Action of the first target
brings the client back to the front (`activate`, below).

**In the window:**

- **left click**: a target, snapped to the nearest point of a platform the
  character can reach from where it stands. The window says when the click was
  off every platform, or on a platform the character can't reach from here.
- **r**: a random reachable target, drawn as the rotation draws one (on the
  reachable platforms, weighted by their width: `WorldMap.random_point`).
- **n**: `--series` random targets in a row, each one once the last has ended.
- **Esc**: cancel the target (and the series).
- **q**, or closing the window: quit. The Session stops.

A new target while one runs replaces it. **Bringing this window to the front
while an Action is in flight cancels the target**: the bot's keys go to
whichever window is in front, so they would land here.

**What it shows** for each target: the planned route (the Path's moves, drawn
on the map), the live state (the cycle, the plan being sent, the position's
source and its error to the target, whether an Action is in flight), and the
result when it ends: `arrived` with the final error in virtual px and the time,
`timed out`, `stuck` (timed out with the Trial driver's stuck events), or
`cancelled`. Every run writes one JSONL file under `trial_records/`
(`<timestamp>-playground.jsonl`), in the Trial record format
(`maple/calibration/records.py`): each target is a one-Trial schedule, with its
own header line (the physics and stats it planned with), its cycles, the
samples read while an Action was in flight, and its outcome. Read it with
`maple.calibration.read_records`.

**It is the bot's own stack.** A real Session (`SessionManager`) runs one bot,
`PlaygroundBot`, from your profile: its `character_class`, its stats
(`speed_multiplier`, `jump_multiplier`) and its `calibration` constants, as
`CalibrationBot` takes them. Its one DecisionMaker, `PlaygroundRunner`, is
`TrialRunner`'s plumbing with targets that come from this window: it reads
the position as `MinimapProvider` does (`PositionReader`, `PositionFusion`),
plans as `PathingProvider` does, on the map's `MovementHandler` (the
`FootholdGraph`, `path_into_movements`), judges each target with the
`TrialDriver` (one Trial per target: its arrival, oscillation and stuck rules),
and ships each Movement Plan as `TrialRunner` and `Rotation` do: an
`ActionRequest` carrying `controller.compile_and_send`, compiled at dispatch
inside the focus lock against the Held-Keys Ledger (ADR 0002). There is no
second movement stack and no second key sender. The window runs in its own process
and sends nothing to the game: it only passes your commands to the
DecisionMaker.

**What it needs:** the MapleStory client open, on the map you name, with the
minimap **already expanded** (the playground refuses to start rather than
press the minimap key); the game data store (`python -m game_data extract`);
`configs/recordings.ini` and the profile's `configs/keybindings.ini` section;
and a profile under `profiles/` (`--profile`, or the only one there besides the
example). The profile's `bot:` is ignored. Its `map` is replaced by `--map`
when given. With `--map auto` the map is identified as `MapleBot` does it, from
the minimap's banner when it is shown (it waits up to `map_check.WINDOW` for
it), else from the expanded minimap alone, which the canvas match can still
tell. It never presses the minimap key to show the banner.

**Which keys reach the game, and when (C-KEYS).** This script sends keys,
unlike the other toolkit scripts.

- **At start, nothing but key-ups.** `SessionManager` sweeps the keyboard
  (`release_all` on the window in front), as every Session does: key-ups for
  keys found held. The minimap is checked, never toggled.
- **Nothing while no target runs.** The position is read from the screen;
  nothing is sent until you click the map or press r or n.
- **While a target runs:** the Movement Plans' keys, to the client: the arrow
  keys, the profile's `jump` key, and the `Teleport` skill's key when the
  class has it. Before an Action's first key, when the client isn't in front
  (you clicked this window), the bot brings it to the front as every Session
  does. That is `activate`: under the focus lock, `release_all` on the window
  in front, an Alt tap there, then `SetForegroundWindow` on the client.
  The minimap's error handler (which moves the mouse and toggles the minimap)
  is never called: a position that can't be read is `UNSURE`, and the target
  holds until one is.
- **Whenever a target ends** (arrived, timed out, cancelled, replaced), and on
  every way out: `release_every_key`, at `FAILSAFE` priority, cancelling the
  Movement Action in flight (it shares their name). It **brings the client to
  the front first**, so **every target end, arrivals and timeouts included,
  switches the focus to the client**. It uses the same `activate` an Action
  starts with: with another window in front, it waits for the focus lock,
  runs `release_all` on that window, taps Alt there, then calls
  `SetForegroundWindow` on the client. With the client already in front, it
  takes the lock if it's free, else goes on without it. It does this because
  `SendInput` delivers key-ups to the window in front, and when you press Esc
  or q, click a new target, or bring this window forward, that window is this
  one. It then sends key-ups for every key the Held-Keys Ledger holds and for
  every key a Movement Plan presses (the arrows, `jump`, `Teleport`). That
  covers a cancelled Action whose own key-ups went to this window while the
  ledger marked them released. Last comes `release_all`'s sweep for keys found
  physically down. The sweep runs only while the playground's own keys (q, r,
  n, Escape) can't be among the keys it reads, so your Esc or q is never taken
  for a key the bot holds. This focus switch on release is the playground's
  own; the shared `release_all` is unchanged.
- **Every exit ends with every key released:** `q` and closing the window
  quit (the window sends `quit`, the DecisionMaker releases and asks the
  Session to stop); an exception in the window or a killed window process is
  seen by Main Process within `WATCH_INTERVAL`, which sends `quit` and asks the
  Session to stop; an exception in the DecisionMaker releases on its way out
  and takes the Engine down. However the Session ends, `SessionManager` also
  runs `release_all` for the client's handle on exit (ADR 0002). That last one
  is the shared path: it doesn't bring the client forward, so its key-ups
  reach whichever window is in front. The playground's own release, above,
  has already run by then on every path but a killed Engine.

Keys pressed in this window are read by the window only. The playground's own
keys must not be the game's `jump` or `Teleport` key (the bot's keys could land
here for an instant before a cancel): it refuses to start if one is.

**What can't be verified offline:** that the window draws and the clicks land
where they point against the live client, that the character reaches the
targets, how the focus switch behaves when this window is clicked mid-run,
whether `activate` brings the client to the front before a release (a
minimised client, or one Windows won't foreground, would leave the key-ups in
this window), and whether `--map auto` tells the map without the banner. The
orchestrator runs it live, then the maintainer.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import math
import multiprocessing
import multiprocessing.connection
import multiprocessing.managers
import queue
import random
import sys
import time
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
import win32gui

import maple.parsers
from botting import PARENT_LOG, controller
from botting.controller import HeldKeysLedger
from botting.controller.inputs import SharedResources
from botting.controller.inputs.focused_inputs import activate
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.core.session_manager import SessionManager
from botting.screen import Reading
from botting.stop_file import request_stop
from maple.actions import priorities
from maple.actions.menus import minimap_banner_shown, minimap_state
from maple.bots import map_check
from maple.bots.maple_bot import MapleBot
from maple.calibration import (
    JsonlRecordWriter,
    MovementSummary,
    RecordSink,
    TrialBatch,
    TrialDriver,
    TrialOutcome,
    TrialSchedule,
    TrialSpec,
    default_record_path,
    summarize_plan,
)
from maple.calibration.driver import COARSE_SLACK
from maple.calibration.records import CycleRecord, TrialResult
from maple.decision_makers.providers import (
    CALIBRATION,
    CHARACTER,
    FRAME,
    GAME_PHYSICS,
    HANDLE,
    MINIMAP_READER,
    POSITION_FUSION,
    PROFILE_JUMP_MULTIPLIER,
    PROFILE_SPEED_MULTIPLIER,
    WORLD_MAP,
    MinimapProvider,
    MovementPlan,
    PositionReader,
    actionable,
)
from maple.decision_makers.providers.pathing import read_resolution
from maple.decision_makers.trial_runner import (
    HEADER_READS,
    TrialRunner,
    coarse_slack,
    schedule_header,
)
from maple.launchers.profile import ProfileError, available, load
from maple.launchers.run import check_configs
from maple.model.mechanics import MovementHandler, compile_movements
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraph, FootholdGraphs
from maple.model.navigation import Path as GraphPath
from maple.model.navigation.foothold_graph import PLACE_TOLERANCE
from maple.model.world import Platform, WorldMap
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState, MinimapView
from maple.screen.position import PositionSource, VirtualPosition
from maple.screen.sprites import StartupRefused

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

type Point = tuple[float, float]
type Target = tuple[int, int]

#: Arrival, in virtual px: the Trial schedules' usual tolerance.
DEFAULT_TOLERANCE: Final = 16.0
#: Seconds a target may take before it times out.
DEFAULT_BUDGET: Final = 60.0
#: Random targets in a row, for `n`.
DEFAULT_SERIES: Final = 10
#: The map's height in the window, in screen px.
DEFAULT_HEIGHT: Final = 800

#: The schedule name of every target, and the record file's suffix.
SCHEDULE: Final = "playground"
#: Seconds the Trial's positioning phase may take. Its start is where the
#: character was read when the target began, so it arrives on its first cycle;
#: it is only there because a Trial has one.
SETUP_BUDGET: Final = 2.0
#: How far, in virtual px, a random target is drawn from the character at least
#: (when the reachable platforms allow): a target it already stands on teaches
#: nothing.
RANDOM_AWAY: Final = 4 * DEFAULT_TOLERANCE
#: Draws before a random target close to the character is accepted anyway.
RANDOM_DRAWS: Final = 20

#: Seconds this window may stay in front with an Action in flight before the
#: target is cancelled: long enough for the bot's own focus switch, at an
#: Action's start, to bring the client back.
FRONT_GRACE: Final = 0.25
#: Seconds between two looks at whether the window process is still there.
WATCH_INTERVAL: Final = 0.2
#: Milliseconds the window waits for a key between two draws.
REFRESH_MS: Final = 50

# The commands the window sends to the DecisionMaker, as `(kind, payload)`.
CLICK: Final = "click"
RANDOM: Final = "random"
SERIES: Final = "series"
CANCEL: Final = "cancel"
QUIT: Final = "quit"

#: The window's keys, by `cv2.waitKeyEx` code, and their names as
#: `configs/keybindings.ini` writes them.
KEYS: Final[dict[int, str]] = {
    ord("q"): QUIT,
    ord("Q"): QUIT,
    ord("r"): RANDOM,
    ord("R"): RANDOM,
    ord("n"): SERIES,
    ord("N"): SERIES,
    27: CANCEL,
}
KEY_NAMES: Final[dict[str, str]] = {
    "q": QUIT,
    "r": RANDOM,
    "n": SERIES,
    "escape": CANCEL,
}
#: The bindings a Movement Plan presses besides the arrow keys.
MOVEMENT_BINDINGS: Final = ("jump", "Teleport")


# ------------------------------------------------------------- choosing targets


@dataclass(frozen=True)
class Choice:
    """A target, or `None` with why there is none; `note` is what the window
    says about it."""

    target: Target | None
    note: str


def nearest_point(platform: Platform, point: Point) -> tuple[float, Point]:
    """The point of `platform` nearest `point`, along its footholds, and how far
    it is."""
    px, py = point
    best: tuple[float, Point] | None = None
    for f in platform.footholds:
        dx, dy = f.x2 - f.x1, f.y2 - f.y1
        length2 = dx * dx + dy * dy
        t = 0.0
        if length2 > 0:
            t = min(1.0, max(0.0, ((px - f.x1) * dx + (py - f.y1) * dy) / length2))
        on = (f.x1 + t * dx, f.y1 + t * dy)
        distance = math.hypot(px - on[0], py - on[1])
        if best is None or distance < best[0]:
            best = (distance, on)
    assert best is not None, "a platform has footholds"
    return best


def _nearest(
    platforms: Iterable[Platform], point: Point
) -> tuple[float, Point, Platform] | None:
    best: tuple[float, Point, Platform] | None = None
    for platform in platforms:
        distance, on = nearest_point(platform, point)
        if best is None or distance < best[0]:
            best = (distance, on, platform)
    return best


def _whole(point: Point) -> Target:
    return round(point[0]), round(point[1])


def snap_target(
    click: Point, reachable: Sequence[Platform], platforms: Sequence[Platform]
) -> Choice:
    """
    The point nearest `click` on a platform of `reachable`. The note says when
    the click was off every platform of the map (`platforms`), farther than the
    graph places a point (`PLACE_TOLERANCE`), or nearer a platform the
    character can't reach from here.
    """
    nearest = _nearest(reachable, click)
    if nearest is None:
        return Choice(None, "no platform is reachable from here")
    distance, on, _ = nearest
    target = _whole(on)
    anywhere = _nearest(platforms, click)
    if anywhere is None or anywhere[0] > PLACE_TOLERANCE:
        note = (
            f"the click is off every platform: target {target}, the nearest "
            f"reachable point, {distance:.0f} px away"
        )
    elif anywhere[2] not in reachable:
        note = (
            f"the clicked platform is unreachable from here: target {target}, "
            f"the nearest reachable point, {distance:.0f} px away"
        )
    else:
        note = f"target {target}"
    return Choice(target, note)


def random_target(
    world_map: WorldMap,
    reachable: Sequence[Platform],
    position: Point | None,
    rng: random.Random,
    away: float = RANDOM_AWAY,
) -> Choice:
    """
    A random point on `reachable`, drawn as the rotation draws its targets
    (`WorldMap.random_point`), at least `away` from `position` when one of
    `RANDOM_DRAWS` draws is.
    """
    point: Point | None = None
    try:
        for _ in range(RANDOM_DRAWS):
            point = world_map.random_point(reachable, rng)
            if position is None or math.dist(point, position) >= away:
                break
    except ValueError as error:
        return Choice(None, f"no random target: {error}")
    assert point is not None
    target = _whole(point)
    return Choice(target, f"random target {target}")


def reachable_platforms(graph: FootholdGraph, position: Point) -> tuple[Platform, ...]:
    """
    The platforms some Path on `graph` reaches from `position`.

    :raises ValueError: `position` is on no platform or rope.
    """
    return tuple(s for s in graph.reachable(position) if isinstance(s, Platform))


def describe_outcome(outcome: TrialOutcome, why: str = "cancelled") -> str:
    """One line for a target that ended: how, the final error, and the time."""
    error = (
        "no position read"
        if outcome.final_error is None
        else f"final error {outcome.final_error:.1f} px"
    )
    counts = f"{outcome.oscillations} oscillations, {outcome.stuck_events} stuck events"
    if outcome.result == TrialResult.ARRIVED:
        took = outcome.time_to_arrival or outcome.duration
        head = f"arrived in {took:.1f} s, {error}"
    elif outcome.result == TrialResult.TIMEOUT:
        stuck = "stuck: " if outcome.stuck_events else ""
        head = f"{stuck}timed out after {outcome.duration:.1f} s, {error}"
    elif outcome.result == TrialResult.ABANDONED:
        head = f"{why} after {outcome.duration:.1f} s, {error}"
    else:
        head = f"{outcome.result} after {outcome.duration:.1f} s, {error}"
    return f"{outcome.trial} {outcome.target}: {head} ({counts})"


# ---------------------------------------------------------------- the playground


class Playground:
    """
    The targets: which one is next, the Trial judging the one in flight, and
    the rule that **every end releases every key**.

    No client, no pipe, no clock: the DecisionMaker hands it commands, position
    reads and outcomes, and it calls back `new_driver` to make each target's
    Trial and `release` whenever a target ends, is cancelled or replaced, and
    on quit and close. A target asked for is *pending* until a position is
    read; it then becomes a one-Trial schedule whose start is that position,
    so the Trial's positioning phase arrives on its first cycle.

    :param reachable: The platforms the character can reach from a position
        (the last one read, or `None`), or why that isn't known.
    :param release: Called with why, to release every key.
    """

    def __init__(
        self,
        world_map: WorldMap,
        *,
        new_driver: Callable[[TrialSchedule], TrialDriver],
        reachable: Callable[[Point | None], tuple[Platform, ...] | str],
        release: Callable[[str], None],
        tolerance: float = DEFAULT_TOLERANCE,
        budget: float = DEFAULT_BUDGET,
        series: int = DEFAULT_SERIES,
        rng: random.Random | None = None,
    ) -> None:
        self.world_map = world_map
        self.new_driver = new_driver
        self.reachable = reachable
        self.release = release
        self.tolerance = tolerance
        self.budget = budget
        self.series = series
        self.rng = rng or random.Random()
        self.pending: Target | None = None
        self.driver: TrialDriver | None = None
        self.position: Point | None = None
        self.series_left = 0
        self.count = 0
        self.quitting = False
        self.note = "click the map, or press r, to send the character somewhere"
        self.results: list[str] = []

    @property
    def target(self) -> Target | None:
        """The target pending or in flight."""
        if self.driver is not None and self.driver.trial is not None:
            return self.driver.trial.target
        return self.pending

    @property
    def running(self) -> bool:
        """A target is pending or in flight."""
        return self.target is not None

    # --- commands ----------------------------------------------------------------

    def handle(self, kind: str, payload: object, now: float) -> None:
        """One command from the window. After `QUIT`, every command is ignored."""
        if self.quitting:
            return
        if kind == QUIT:
            self.quit(str(payload or "quit"), now)
        elif kind == CANCEL:
            self.cancel(str(payload or "cancelled"), now)
        elif kind == CLICK:
            self.series_left = 0
            self._click(payload, now)
        elif kind == RANDOM:
            self.series_left = 0
            self._random(now)
        elif kind == SERIES:
            self.series_left = max(0, self.series - 1)
            self._random(now)
        else:
            self.note = f"unknown command {kind!r}"

    def _click(self, payload: object, now: float) -> None:
        if not (isinstance(payload, Sequence) and len(payload) == 2):
            self.note = f"a click needs (x, y), not {payload!r}"
            return
        x, y = payload
        reachable = self.reachable(self.position)
        if isinstance(reachable, str):
            self.note = f"no target: {reachable}"
            return
        self._set(
            snap_target((float(x), float(y)), reachable, self.world_map.platforms), now
        )

    def _random(self, now: float) -> None:
        reachable = self.reachable(self.position)
        if isinstance(reachable, str):
            self.series_left = 0
            self.note = f"no random target: {reachable}"
            return
        self._set(
            random_target(self.world_map, reachable, self.position, self.rng), now
        )

    def _set(self, choice: Choice, now: float) -> None:
        if choice.target is None:
            self.series_left = 0
            self.note = choice.note
            return
        if self.running:
            self._end("replaced", now)
        self.pending = choice.target
        self.note = choice.note

    # --- the target's life ---------------------------------------------------------

    def start(
        self, position: Reading[VirtualPosition], now: float
    ) -> TrialDriver | None:
        """
        Take this cycle's position; turn a pending target into its Trial when
        the position is read. The Trial in flight, if any.
        """
        if position.value is not None:
            self.position = (float(position.value.x), float(position.value.y))
        if self.pending is None or self.driver is not None:
            return self.driver
        if position.value is None:
            self.note = f"waiting for a position read ({position.status.value})"
            return None
        assert self.position is not None
        self.count += 1
        name = f"target-{self.count}"
        trial = TrialSpec(
            name,
            _whole(self.position),
            self.pending,
            self.tolerance,
            self.budget,
            setup_budget=SETUP_BUDGET,
        )
        schedule = TrialSchedule(
            SCHEDULE, self.world_map.id, (TrialBatch(name, (trial,)),)
        )
        self.driver = self.new_driver(schedule)
        self.pending = None
        return self.driver

    def finish(self, outcome: TrialOutcome, now: float) -> None:
        """The Trial in flight closed: say how, release, and go on with a series."""
        self.driver = None
        self.results.append(describe_outcome(outcome))
        self.note = self.results[-1]
        self.release(f"{outcome.trial} {outcome.result}")
        if self.series_left > 0:
            self.series_left -= 1
            self._random(now)

    def cancel(self, why: str, now: float) -> None:
        """Drop the target and the series, and release when there was one.
        With nothing running nothing is sent: no key was pressed for it."""
        self.series_left = 0
        self._end(why, now, always=False)
        self.note = why

    def quit(self, why: str, now: float) -> None:
        """End the target, release whatever ran, and take no command after."""
        self.series_left = 0
        self._end(why, now, always=True)
        self.note = why
        self.quitting = True

    def close(self, now: float) -> None:
        """The DecisionMaker is ending: abandon the target, and release."""
        self.series_left = 0
        self._end("the playground ended", now, always=True)

    def _end(self, why: str, now: float, *, always: bool = True) -> None:
        """End the target in flight or pending, then release: whenever there was
        one, and with `always` even when there wasn't (a way out)."""
        driver, self.driver = self.driver, None
        ended = driver is not None or self.pending is not None
        if driver is not None:
            outcome = driver.abandon(now)
            if outcome is not None:
                self.results.append(describe_outcome(outcome, why))
        elif self.pending is not None:
            self.results.append(f"target {self.pending}: {why} before it started")
        self.pending = None
        if ended or always:
            self.release(why)


# ------------------------------------------------------------- the Engine side


@dataclass(frozen=True)
class PlaygroundLink:
    """
    The window's way to the DecisionMaker and back: Manager proxies, so they
    cross into the Engine inside the bot's settings.

    :ivar commands: `(kind, payload)` from the window (and from Main Process's
        window watch), read by the DecisionMaker every cycle.
    :ivar view: ``"snapshot"``, the DecisionMaker's last state for the window
        to draw, and ``"ended"``, set when the Session is over.
    """

    commands: Any
    view: Any


def movement_keys(binds: Mapping[str, str]) -> frozenset[str]:
    """Every key a Movement Plan presses: the arrows, `jump`, and `Teleport`."""
    keys = set(controller.OPPOSITES)
    keys.update(str(binds[b]) for b in MOVEMENT_BINDINGS if b in binds)
    return frozenset(keys)


async def release_every_key(handle: int, ign: str) -> None:
    """
    In Main Process: release every key **in the client**, whichever window is
    in front.

    1. `activate(handle)`, as an Action starts: it takes the focus lock (so it
       waits for a cancelled Movement Action to let go) and, with another
       window in front, taps Alt there and brings the client to the front.
       Key-ups go to the window in front, so this is what makes them reach the
       client when a command typed in the playground's window ended the target.
    2. Key-ups for the keys the Held-Keys Ledger holds and for every key a
       Movement Plan presses (`movement_keys`): a cancelled Action released
       its keys to the window that was in front, and the ledger counts them
       released.
    3. `release_all`'s sweep for keys physically down, only while the keys it
       reads can't include the playground's own (`KEY_NAMES`): the
       maintainer's Esc or q must not be taken for a key the bot holds.
       Otherwise the ledger's entry is cleared without a sweep.
    """
    acquired = await activate(handle)
    try:
        try:
            binds = controller.key_binds(ign)
        except AssertionError:
            # No keybindings section: the arrows and the ledger's keys still go.
            logger.exception("No key bindings for %s: releasing the arrows only.", ign)
            binds = {}
        held = set(HeldKeysLedger.keys_held(handle))
        controller.release_keys(sorted(held | movement_keys(binds)), handle)
        if HeldKeysLedger.sweep_candidates().isdisjoint(KEY_NAMES):
            controller.release_all(handle)
        else:
            HeldKeysLedger.clear(handle)
    finally:
        if acquired:
            SharedResources.focus_lock.release()


class PlaygroundRunner(DecisionMaker):
    """
    `TrialRunner`'s plumbing, with targets from the playground's window.

    Each cycle it takes the window's commands, reads the position, and, while
    a target runs, plans the Path to the Trial's target, hands the cycle to the
    `TrialDriver` and ships the Movement Plan as `TrialRunner` does: one Action
    at a time, under its lock, an `ActionRequest` carrying
    `controller.compile_and_send`. While no target runs it only reads the
    position and publishes it. It publishes its state for the window every
    cycle.

    It differs from `TrialRunner` in what it presses outside a plan: nothing.
    It builds neither `MinimapProvider`, whose setup shows the minimap and
    whose position has an error handler that sends input, nor
    `PathingProvider`, which plans from that position to `DESTINATION`. It
    reads its own position off the Bot-level readers (`_quiet_position`: a
    read that fails is `UNSURE`), and plans its own Path to its own target on
    the map's `MovementHandler`, as `PathingProvider` plans one. Every end of
    a target releases every key (`release_every_key`), and so does the end of
    its loop.
    """

    screen_readers = (MINIMAP,)
    reads = (
        HANDLE,
        CHARACTER,
        WORLD_MAP,
        FRAME,
        MINIMAP_READER,
        POSITION_FUSION,
        *HEADER_READS,
    )

    _throttle = TrialRunner._throttle

    #: Seconds a minimap reading is used before a position read reads it
    #: again, as `MinimapProvider` serves it.
    MINIMAP_REFRESH = MinimapProvider.REFRESH

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        playground: PlaygroundLink | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
        budget: float = DEFAULT_BUDGET,
        series: int = DEFAULT_SERIES,
        **kwargs: object,
    ) -> None:
        """
        :param playground: The window's link; set by `toolkit.movement_playground`.
        :param kwargs: The profile's other settings (a `trial_schedule`, say),
            which this DecisionMaker doesn't read.
        """
        super().__init__(metadata, data, pipe)
        if playground is None:
            raise ValueError(
                f"{self} is the movement playground's DecisionMaker: run "
                "`python -m toolkit.movement_playground`."
            )
        self._link = playground
        self._tolerance = tolerance
        self._budget = budget
        self._series = series

    def setup(self) -> None:
        """The lock, the record, the minimap's first reading and the handler."""
        self.lock = self._proxies.instance(repr(self), "Lock")
        path = default_record_path(SCHEDULE)
        self._setup(
            self._link,
            JsonlRecordWriter(path),
            tolerance=self._tolerance,
            budget=self._budget,
            series=self._series,
        )
        logger.info("%s records to %s", self, path)

    def _setup(
        self,
        link: PlaygroundLink,
        writer: RecordSink,
        *,
        tolerance: float,
        budget: float,
        series: int,
        rng: random.Random | None = None,
    ) -> None:
        """Everything after the Session's proxies: what an offline check builds."""
        self.link = link
        self._writer = writer
        self._record = str(getattr(writer, "path", ""))
        world_map = self._world_map()
        self._minimap_reading: Reading[MinimapView] | None = None
        self._minimap_read_at = float("-inf")
        self._position_reader = PositionReader(
            self,
            self.emit,
            fusion=lambda: self.read(POSITION_FUSION),
            minimap=self._read_minimap,
            frame=lambda: self.read(FRAME),
        )
        self._read_minimap()
        self._position: Reading[VirtualPosition] = Reading.unsure(0.0, "not read yet")
        self._graphs: dict[bool, FootholdGraphs] = {}
        self._path_read_at: float | None = None
        self.movement_handler = self._new_handler()
        if self.movement_handler is not None:
            # Built now, off the loop, so the first Path doesn't wait for it.
            self.movement_handler.graphs.prepare(self._physics())
        self.playground = Playground(
            world_map,
            new_driver=self._new_driver,
            reachable=self._reachable,
            release=self._release,
            tolerance=tolerance,
            budget=budget,
            series=series,
            rng=rng,
        )
        self._last_target: Point = (0.0, 0.0)
        self._route: list[list[object]] = []
        self._plan = ""
        self._cycle: CycleRecord | None = None
        self._stopped = False

    # --- what it reads -------------------------------------------------------------

    def _read_minimap(self) -> Reading[MinimapView]:
        """
        The minimap's reading of the current frame, read again once it is
        older than `MINIMAP_REFRESH`, as `MinimapProvider` serves it.
        """
        reading = self._minimap_reading
        if (
            reading is None
            or time.monotonic() - self._minimap_read_at > self.MINIMAP_REFRESH
        ):
            reader = self.read(MINIMAP_READER)
            assert reader is not None, "a MapleBot always has a minimap reader"
            reading = reader.read(self.read(FRAME))
            self._minimap_reading = reading
            self._minimap_read_at = time.monotonic()
        return reading

    def _quiet_position(self) -> Reading[VirtualPosition]:
        """The position, read now (`PositionReader`); a read that raises is `UNSURE`."""
        try:
            return self._position_reader()
        except ValueError as error:
            return Reading.unsure(time.monotonic(), str(error))

    def _reachable(self, position: Point | None) -> tuple[Platform, ...] | str:
        """The platforms reachable from `position`, or why that isn't known."""
        handler = self.movement_handler
        if handler is None:
            return "this map plans no Path"
        graph = handler.ready_graph(self._physics())
        if graph is None:
            return "the foothold graph is still building; try again in a moment"
        if position is None:
            return "no position read yet"
        try:
            platforms = reachable_platforms(graph, position)
        except ValueError:
            return "the character is on no platform or rope; try again once it lands"
        return platforms or "no platform is reachable from here"

    def _virtual_target(self) -> Point:
        """The Trial's target (its start while positioning); the last one after."""
        driver = self.playground.driver
        target = None if driver is None else driver.target
        if target is not None:
            self._last_target = (float(target[0]), float(target[1]))
        return self._last_target

    # --- planning, as `PathingProvider` plans ----------------------------------------

    def _world_map(self) -> WorldMap:
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            raise ValueError(
                "no map to plan on: the bot's map isn't known, or has no minimap"
            )
        return world_map

    def _new_handler(self) -> MovementHandler | None:
        """
        The map's `MovementHandler`, made once, at setup; `None`, logged, on a
        map with no minimap or none known, where nothing is planned.
        """
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            logger.warning(
                "%s plans no Path: the bot's map isn't known, or has no minimap.",
                self,
            )
            return None
        teleport = self.read(CHARACTER).skills.get("Teleport")
        can_teleport = teleport is not None
        graphs = self._graphs.get(can_teleport)
        if graphs is None:
            graphs = self._graphs[can_teleport] = FootholdGraphs(
                world_map, teleport=can_teleport
            )
        return MovementHandler(
            self.read(HANDLE), world_map, self.data.ign, teleport, graphs=graphs
        )

    def _physics(self) -> VRPhysics:
        """The character's physics: the game's, with the profile's stats."""
        values = self.read(GAME_PHYSICS)
        if values is None:
            raise ValueError("no game physics: the bot's map isn't known")
        return VRPhysics.from_game_files(
            values,
            speed_multiplier=self.read(PROFILE_SPEED_MULTIPLIER),
            jump_multiplier=self.read(PROFILE_JUMP_MULTIPLIER),
            calibration=self.read(CALIBRATION),
        )

    def _plan_path(self) -> GraphPath | None:
        """The Path from this cycle's position to the target; `None` holds."""
        handler = self.movement_handler
        if handler is None:
            return None
        reading = self._position
        if reading.value is None:
            logger.debug("No Path: the position is unsure (%s).", reading.detail)
            return None
        physics = self._physics()
        graph = handler.ready_graph(physics)
        if graph is None:
            logger.debug("No Path: the foothold graph of the current stats builds.")
            return None
        # The frame the Path starts from: the compile leads the plan by how far
        # the character has walked since (`_movement_compiler`).
        self._path_read_at = reading.frame_time
        return handler.compute_path(
            (float(reading.value.x), float(reading.value.y)),
            self._virtual_target(),
            physics,
            graph=graph,
            resolution=read_resolution(reading.value, self._world_map()),
        )

    def _plan_movements(self, path: GraphPath | None) -> MovementPlan:
        """The Movement Plan of `path`; empty with no handler."""
        handler = self.movement_handler
        if handler is None:
            return ()
        return handler.path_into_movements(path)

    def _movement_compiler(self, movements: MovementPlan) -> functools.partial:
        """
        `movements`' compile, its inputs frozen into a picklable callable, as
        `PathingProvider.compiler` freezes them: the Action duration cap is
        `TrialRunner`'s default, and the plan leads by how far the character
        walked since the frame its Path was planned from.
        """
        physics = self._physics()
        return functools.partial(
            compile_movements,
            movements=movements,
            handle=self.read(HANDLE),
            ign=self.data.ign,
            speed=physics.walk_speed,
            climb_speed=physics.climb_speed,
            teleport=self.read(CHARACTER).skills.get("Teleport"),
            total_duration=TrialRunner.DEFAULT_ACTION_DURATION,
            always_release=False,
            walk_acceleration=physics.walk_acceleration,
            walk_deceleration=physics.walk_deceleration,
            read_at=self._path_read_at,
            correlation_id=self.correlation_id,
        )

    # --- the decision cycle --------------------------------------------------------

    def on_stop(self) -> None:
        """
        However the decision loop ended, the target ends and keys are released:
        the Supervisor calls this once the loop has stopped, by any route.
        """
        self._close()

    async def _decide(self) -> None:
        if self._stopped:
            return
        now = time.monotonic()
        self._take_commands(now)
        if self._stopped:
            return
        self._position = position = self._quiet_position()
        driver = self.playground.start(position, now)
        if driver is None:
            self._route, self._plan, self._cycle = [], "", None
            self._publish(position, in_flight=False)
            return
        # One Action in flight at a time, as `TrialRunner`: a cycle that can't
        # dispatch is a sample, which judges nothing.
        if not self.lock.acquire(blocking=False):
            driver.sample(position, now)
            self._publish(position, in_flight=True)
            return
        dispatched = False
        try:
            path = self._plan_path()
            movements = self._plan_movements(path)
            self._route = _route(path)
            self._plan = _plan_text(summarize_plan(movements))
            verdict = driver.advance(
                position, now, plan=movements, correlation_id=self.correlation_id
            )
            self._cycle = verdict.cycle
            if verdict.outcome is not None:
                logger.info("%s %s", self, describe_outcome(verdict.outcome))
                self.playground.finish(verdict.outcome, now)
            elif verdict.dispatch and actionable(movements):
                self.send(self._request(movements))
                dispatched = True
        finally:
            if not dispatched:
                self.lock.release()
        self._publish(position, in_flight=dispatched)

    def _take_commands(self, now: float) -> None:
        """Every command the window sent since the last cycle, in order."""
        while not self._stopped:
            try:
                kind, payload = self.link.commands.get_nowait()
            except queue.Empty:
                return
            self.playground.handle(kind, payload, now)
            if self.playground.quitting:
                self._stop(str(payload or "quit"))

    def _request(self, movements: MovementPlan) -> ActionRequest:
        """The Action `TrialRunner` and `Rotation` send: a Movement Plan,
        compiled at dispatch."""
        return ActionRequest(
            f"{self}",
            controller.compile_and_send,
            ign=self.data.ign,
            requeue_if_not_scheduled=False,
            callbacks=[self.lock.release],
            args=(self.read(HANDLE), self._movement_compiler(movements)),
        )

    def _release_request(self) -> ActionRequest:
        """`release_every_key` (the client brought to the front, then every key
        released), cancelling the Movement Action in flight (its callback
        releases the lock)."""
        return ActionRequest(
            f"{self} - Releasing every key",
            release_every_key,
            ign=self.data.ign,
            priority=priorities.FAILSAFE,
            cancels_itself=True,
            cancel_tasks=[f"{self}"],
            requeue_if_not_scheduled=True,
            args=(self.read(HANDLE), self.data.ign),
        )

    def _release(self, why: str) -> None:
        """Ask Main Process to release every key. Never raises: it runs on every
        way out, an exception's included."""
        logger.info("%s releases every key: %s", self, why)
        try:
            self.send(self._release_request())
        except OSError:
            logger.exception("%s could not ask for the keys to be released.", self)

    # --- Trials ----------------------------------------------------------------------

    def _new_driver(self, schedule: TrialSchedule) -> TrialDriver:
        return TrialDriver(
            schedule,
            self._writer,
            header=schedule_header(schedule, self),
            coarse_slack=coarse_slack(self.read(WORLD_MAP)),
        )

    # --- ending ----------------------------------------------------------------------

    def _stop(self, why: str) -> None:
        """Quit: decide no more, and ask the Session to stop (the stop file)."""
        self._stopped = True
        session_dir = self.metadata.get("session_dir")
        if session_dir is None:
            return
        try:
            request_stop(Path(session_dir), f"movement playground: {why}")
        except OSError:
            logger.exception("%s could not ask the Session to stop.", self)

    def _close(self) -> None:
        """The loop's end: the target abandoned, keys released, the file closed."""
        self.playground.close(time.monotonic())
        self._writer.close()
        try:
            self.link.view["ended"] = "the playground's DecisionMaker ended"
        except OSError, EOFError:
            pass

    # --- the window's view -----------------------------------------------------------

    def _publish(self, position: Reading[VirtualPosition], *, in_flight: bool) -> None:
        """This cycle's state, for the window to draw."""
        try:
            self.link.view["snapshot"] = self._snapshot(position, in_flight=in_flight)
        except OSError, EOFError:
            logger.debug("%s: the window's view is gone.", self)

    def _snapshot(
        self, position: Reading[VirtualPosition], *, in_flight: bool
    ) -> dict[str, object]:
        playground = self.playground
        value = position.value
        world_map = playground.world_map
        cycle = self._cycle
        handler = self.movement_handler
        graph = None if handler is None else handler.ready_graph(self._physics())
        return {
            "map_id": world_map.id,
            "map": ": ".join(p for p in (world_map.street, world_map.name) if p),
            "position": None if value is None else (float(value.x), float(value.y)),
            "status": position.status.value,
            "source": None if value is None else str(value.source),
            "coarse": value is not None and value.source is PositionSource.COARSE,
            "detail": position.detail,
            "target": playground.target,
            "pending": playground.pending is not None,
            "running": playground.running,
            "in_flight": in_flight,
            "phase": None if cycle is None else cycle.phase,
            "cycle": None if cycle is None else cycle.cycle,
            "elapsed": None if cycle is None else cycle.elapsed,
            "error": None if cycle is None else cycle.error,
            "plan": self._plan,
            "route": self._route,
            "note": playground.note,
            "results": playground.results[-6:],
            "series_left": playground.series_left,
            "graph": "ready" if graph is not None else "building",
            "tolerance": playground.tolerance,
            "record": self._record,
            "time": time.monotonic(),
        }


def _route(path: GraphPath | None) -> list[list[object]]:
    """A Path's moves as `[kind, direction, x1, y1, x2, y2]`, for the window."""
    if path is None:
        return []
    return [
        [
            str(m.kind),
            None if m.direction is None else str(m.direction),
            *m.start,
            *m.end,
        ]
        for m in path.moves
    ]


def _plan_text(plan: Sequence[MovementSummary]) -> str:
    """A Movement Plan in one line: each component's type, and its length."""
    parts = [
        f"{m.movement_type} {m.length:.0f}" if m.length else m.movement_type
        for m in plan
        if m.movement_type != "END_OF_MOVEMENT"
    ]
    return ", ".join(parts)


class PlaygroundBot(MapleBot):
    """
    The playground's bot: one DecisionMaker, `PlaygroundRunner`, as
    `CalibrationBot` has one, for the same reason (nothing else moves the
    character, casts, or opens a menu while a target is judged).

    It checks the minimap at start without pressing its key: a minimap that
    isn't expanded refuses the start.
    """

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [PlaygroundRunner]

    def _show_minimap(self, minimap: MinimapReader, *, banner: bool) -> None:
        """
        That the minimap is expanded, read for `map_check.WINDOW` seconds; never
        pressed (the playground sends nothing before a target). With `banner`
        (`map: auto`), as `MapleBot._show_minimap`: the banner first, for the
        whole window, then any expanded look, which the canvas match can still
        tell the map from.

        :raises StartupRefused: It isn't expanded.
        """
        assert self.data is not None
        handle = self.data.handle
        start = time.monotonic()
        while True:
            state = minimap_state(minimap, handle)
            expanded = state is MinimapState.EXPANDED
            if expanded and (not banner or minimap_banner_shown(minimap, handle)):
                return
            if time.monotonic() - start >= map_check.WINDOW:
                if expanded:
                    logger.warning(
                        "The minimap's banner isn't shown: map: auto tells the map "
                        "from the expanded minimap alone."
                    )
                    return
                raise StartupRefused(
                    f"The minimap isn't expanded (read {state}). The playground "
                    "presses no key before a target: expand the minimap in the "
                    "client, then start it again."
                )
            time.sleep(map_check.INTERVAL)


# --------------------------------------------------------------------- the window

PLATFORM_COLOUR: Final = (190, 190, 190)  # BGR
ROPE_COLOUR: Final = (110, 170, 210)
POSITION_COLOUR: Final = (255, 0, 255)
COARSE_COLOUR: Final = (255, 200, 0)
TARGET_COLOUR: Final = (60, 60, 255)
TEXT_COLOUR: Final = (235, 235, 235)
GREY: Final = (160, 160, 160)
GOOD: Final = (80, 220, 80)
ROUTE_COLOURS: Final[dict[str, tuple[int, int, int]]] = {
    "walk": (80, 220, 80),
    "climb": (230, 220, 60),
    "jump": (0, 165, 255),
    "drop": (60, 60, 255),
    "fall": (60, 60, 255),
    "teleport": (255, 80, 255),
    "portal": (200, 120, 255),
}
PANEL: Final = 520


class MapView:
    """The map, scaled to fit the window: virtual px to window px and back,
    and what is drawn on it."""

    def __init__(self, world_map: WorldMap, height: int, width: int = 1100) -> None:
        self.world_map = world_map
        b = world_map.bounds
        self.left, self.top = b.left, b.top
        w, h = max(1, b.right - b.left), max(1, b.bottom - b.top)
        self.scale = min(height / h, width / w, 1.0)
        self.size = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))

    def to_view(self, point: Sequence[float]) -> tuple[int, int]:
        return (
            round((point[0] - self.left) * self.scale),
            round((point[1] - self.top) * self.scale),
        )

    def to_virtual(self, x: int, y: int) -> Point:
        return x / self.scale + self.left, y / self.scale + self.top

    def contains(self, x: int, y: int) -> bool:
        return 0 <= x < self.size[0] and 0 <= y < self.size[1]

    def base(self, render: np.ndarray | None) -> np.ndarray:
        """The darkened static render, with the platforms and ropes drawn lightly."""
        w, h = self.size
        if render is None:
            img = np.full((h, w, 3), 30, np.uint8)
        else:
            small = cv2.resize(render, (w, h), interpolation=cv2.INTER_AREA)
            alpha = small[..., 3:4].astype(np.float32) / 255
            rgb = small[..., :3].astype(np.float32) * alpha + 30 * (1 - alpha)
            img = np.ascontiguousarray(rgb[..., ::-1] * 0.55).astype(np.uint8)
        for platform in self.world_map.platforms:
            for f in platform.footholds:
                cv2.line(
                    img,
                    self.to_view((f.x1, f.y1)),
                    self.to_view((f.x2, f.y2)),
                    PLATFORM_COLOUR,
                    1,
                    cv2.LINE_AA,
                )
        for rope in self.world_map.ropes:
            cv2.line(
                img,
                self.to_view((rope.x, rope.y1)),
                self.to_view((rope.x, rope.y2)),
                ROPE_COLOUR,
                1,
                cv2.LINE_AA,
            )
        return img

    def draw(self, img: np.ndarray, snapshot: Mapping[str, Any]) -> None:
        """The route, the target and the position."""
        for move in snapshot.get("route") or ():
            kind, _, x1, y1, x2, y2 = move
            cv2.arrowedLine(
                img,
                self.to_view((x1, y1)),
                self.to_view((x2, y2)),
                ROUTE_COLOURS.get(kind, TEXT_COLOUR),
                2,
                cv2.LINE_AA,
                tipLength=0.15,
            )
        target = snapshot.get("target")
        if target is not None:
            at = self.to_view(target)
            radius = max(4, round(float(snapshot.get("tolerance") or 0) * self.scale))
            cv2.circle(img, at, radius, TARGET_COLOUR, 1, cv2.LINE_AA)
            cv2.drawMarker(img, at, TARGET_COLOUR, cv2.MARKER_TILTED_CROSS, 14, 2)
        position = snapshot.get("position")
        if position is not None:
            at = self.to_view(position)
            if snapshot.get("coarse"):
                cv2.circle(img, at, 7, COARSE_COLOUR, 2, cv2.LINE_AA)
            else:
                cv2.rectangle(
                    img,
                    (at[0] - 5, at[1] - 5),
                    (at[0] + 5, at[1] + 5),
                    POSITION_COLOUR,
                    2,
                )


class FrontGuard:
    """
    When to cancel because this window is in front: it has been, with a target
    running and an Action in flight, for `grace` seconds. The bot's keys go to
    the window in front; the grace lets the bot's own focus switch, at an
    Action's start, bring the client back first.
    """

    def __init__(self, grace: float = FRONT_GRACE) -> None:
        self.grace = grace
        self._since: float | None = None

    def update(
        self, *, front: bool, running: bool, in_flight: bool, now: float
    ) -> bool:
        """Whether to cancel now."""
        if not (front and running and in_flight):
            self._since = None
            return False
        if self._since is None:
            self._since = now
            return False
        if now - self._since >= self.grace:
            self._since = None
            return True
        return False


def key_command(code: int) -> str | None:
    """The command of a key pressed in the window, if it has one."""
    return KEYS.get(code)


class Window:
    """The playground's OpenCV window, in its own process."""

    TITLE: Final = "movement playground"

    def __init__(self, link: PlaygroundLink, height: int = DEFAULT_HEIGHT) -> None:
        self.link = link
        self.height = height
        self.guard = FrontGuard()
        self.view: MapView | None = None
        self._base: np.ndarray | None = None
        self._clicks: list[Point] = []
        self._map_id: int | None = None

    def run(self) -> None:
        """Draw and listen until quit, the window closed, or the Session over."""
        cv2.namedWindow(self.TITLE, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.TITLE, self._on_mouse)
        while True:
            if self.link.view.get("ended"):
                return
            snapshot: dict[str, Any] = self.link.view.get("snapshot") or {}
            self._load_map(snapshot)
            cv2.imshow(self.TITLE, self.compose(snapshot))
            code = cv2.waitKeyEx(REFRESH_MS)
            if cv2.getWindowProperty(self.TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return
            command = key_command(code)
            if command == QUIT:
                return
            if command is not None:
                self.send(command, None)
            clicks, self._clicks = self._clicks, []
            for click in clicks:
                self.send(CLICK, click)
            if self.guard.update(
                front=self._in_front(),
                running=bool(snapshot.get("running")),
                in_flight=bool(snapshot.get("in_flight")),
                now=time.monotonic(),
            ):
                self.send(CANCEL, "cancelled: this window came to the front")

    def send(self, kind: str, payload: object) -> None:
        self.link.commands.put((kind, payload))

    def _in_front(self) -> bool:
        hwnd = win32gui.FindWindow(None, self.TITLE)
        return bool(hwnd) and win32gui.GetForegroundWindow() == hwnd

    def _on_mouse(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        view = self.view
        if event == cv2.EVENT_LBUTTONDOWN and view is not None and view.contains(x, y):
            self._clicks.append(view.to_virtual(x, y))

    def _load_map(self, snapshot: Mapping[str, Any]) -> None:
        map_id = snapshot.get("map_id")
        if map_id is None or map_id == self._map_id:
            return
        world_map = WorldMap.load(int(map_id))
        render = None
        if world_map.static_render is not None:
            try:
                render = world_map.static_render.pixels()
            except Exception:
                traceback.print_exc()
        self.view = MapView(world_map, self.height)
        self._base = self.view.base(render)
        self._map_id = int(map_id)

    def compose(self, snapshot: Mapping[str, Any]) -> np.ndarray:
        if self.view is None or self._base is None:
            left = np.full((self.height // 2, 600, 3), 30, np.uint8)
            _put(
                left,
                "waiting for the bot: map check, then the first read",
                (10, 30),
                GREY,
            )
        else:
            left = self._base.copy()
            self.view.draw(left, snapshot)
        right = self._panel(snapshot)
        h = max(left.shape[0], right.shape[0])
        out = np.zeros((h, left.shape[1] + PANEL + 4, 3), np.uint8)
        out[: left.shape[0], : left.shape[1]] = left
        out[: right.shape[0], left.shape[1] + 4 :] = right
        return out

    def _panel(self, s: Mapping[str, Any]) -> np.ndarray:
        def num(value: Any) -> str:
            return "-" if value is None else f"{float(value):.1f}"

        position = s.get("position")
        where = "-" if position is None else f"({position[0]:.0f}, {position[1]:.0f})"
        lines: list[tuple[str, tuple[int, int, int]]] = [
            (f"map {s.get('map_id', '-')} {s.get('map', '')}", TEXT_COLOUR),
            (f"graph {s.get('graph', '-')}", GREY),
            (
                f"POSITION {s.get('status', '-')} {s.get('source') or ''} {where}",
                POSITION_COLOUR if position is not None else TARGET_COLOUR,
            ),
            (f"  {str(s.get('detail') or '')[:70]}", GREY),
            (
                f"TARGET {s.get('target') or '-'}"
                + ("  (pending)" if s.get("pending") else ""),
                TARGET_COLOUR,
            ),
            (
                (
                    f"cycle {s.get('cycle') or '-'} ({s.get('phase') or '-'})  "
                    f"{num(s.get('elapsed'))} s  error {num(s.get('error'))} px"
                ),
                TEXT_COLOUR,
            ),
            (
                "Action in flight" if s.get("in_flight") else "no Action in flight",
                GOOD if s.get("in_flight") else GREY,
            ),
            (f"plan: {str(s.get('plan') or '-')[:66]}", TEXT_COLOUR),
            (f"series left: {s.get('series_left', 0)}", GREY),
            ("", GREY),
            (str(s.get("note") or "")[:76], GOOD),
        ]
        for result in s.get("results") or ():
            lines.append((str(result)[:80], TEXT_COLOUR))
        lines += [
            ("", GREY),
            (f"record: {Path(str(s.get('record') or '-')).name}", GREY),
            ("click: target   r: random   n: series   Esc: cancel   q: quit", GREY),
            ("this window in front while an Action runs cancels it", GREY),
        ]
        img = np.zeros((18 * len(lines) + 10, PANEL, 3), np.uint8)
        for i, (text, colour) in enumerate(lines):
            _put(img, text, (6, 18 + 18 * i), colour)
        return img


def _put(
    img: np.ndarray, text: str, at: tuple[int, int], colour: tuple[int, int, int]
) -> None:
    cv2.putText(img, text, at, cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)


def run_window(link: PlaygroundLink, height: int = DEFAULT_HEIGHT) -> None:
    """
    The window process. However it ends (q, the window closed, an exception,
    Ctrl+C), it sends `QUIT` on its way out, so the target ends and every key
    is released.
    """
    try:
        Window(link, height).run()
    except Exception:
        traceback.print_exc()
    finally:
        try:
            link.commands.put((QUIT, "the window closed"))
        except Exception:
            pass
        cv2.destroyAllWindows()


# ------------------------------------------------------------------------- main


async def watch_window(
    alive: Callable[[], bool],
    link: PlaygroundLink,
    session_dir: Path,
    interval: float = WATCH_INTERVAL,
) -> None:
    """
    In Main Process: once the window process is gone, however it went, send
    `QUIT` (the DecisionMaker ends the target and releases every key) and ask
    the Session to stop (it releases every key again on exit).
    """
    while alive():
        await asyncio.sleep(interval)
    try:
        link.commands.put((QUIT, "the window is gone"))
    except Exception:
        logger.exception("Could not tell the playground's DecisionMaker to quit.")
    request_stop(session_dir, "movement playground: the window is gone")


def close_window(window: multiprocessing.Process, link: PlaygroundLink) -> None:
    """Tell the window the Session is over; stop it if it doesn't go."""
    try:
        link.view["ended"] = "the Session ended"
    except Exception:
        pass
    window.join(timeout=3)
    if window.is_alive():
        window.terminate()


def pick_profile(name: str | None, names: Sequence[str]) -> str:
    """
    `name`, or the only profile besides the example.

    :raises ProfileError: No name, and not exactly one such profile.
    """
    if name:
        return name
    own = [n for n in names if n != "example"]
    if len(own) == 1:
        return own[0]
    listed = ", ".join(own) if own else "none yet (copy profiles/example.yaml)"
    raise ProfileError(f"Name a profile with --profile. Profiles: {listed}.")


def colliding_keys(binds: Mapping[str, str]) -> list[str]:
    """The playground's keys that are also a key a Movement Plan presses."""
    pressed = {str(binds[b]).casefold() for b in MOVEMENT_BINDINGS if b in binds}
    return sorted(k for k in KEY_NAMES if k in pressed)


async def _session(
    ign: str,
    settings: dict[str, Any],
    args: argparse.Namespace,
    *,
    discord: bool,
) -> None:
    """One Session: the bot, the window, and the watch over the window."""
    with SessionManager(
        maple.parsers.MapleParser, recording_section="TEST", discord=discord
    ) as session:
        manager = session.process_manager
        link = PlaygroundLink(manager.Queue(), manager.dict())
        bot = PlaygroundBot(
            ign,
            session.metadata,
            **settings,
            playground=link,
            tolerance=args.tolerance,
            budget=args.budget,
            series=args.series,
        )
        window = multiprocessing.Process(
            target=run_window,
            args=(link, args.height),
            name="Movement playground window",
            daemon=True,
        )
        window.start()
        watch = asyncio.create_task(
            watch_window(window.is_alive, link, session.session_dir),
            name="Movement playground window watch",
        )
        try:
            await session.launch([bot])
        finally:
            watch.cancel()
            close_window(window, link)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m toolkit.movement_playground",
        description="Send the character to targets picked on the map (sends keys).",
    )
    p.add_argument(
        "--map", help="The map's game name, its id, or auto (default: the profile's)."
    )
    p.add_argument("--profile", help="A profile under profiles/, without .yaml.")
    p.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"Arrival, in virtual px (default {DEFAULT_TOLERANCE:g}).",
    )
    p.add_argument(
        "--budget",
        type=float,
        default=DEFAULT_BUDGET,
        help=f"Seconds a target may take (default {DEFAULT_BUDGET:g}).",
    )
    p.add_argument(
        "--series",
        type=int,
        default=DEFAULT_SERIES,
        help=f"Random targets in a row for n (default {DEFAULT_SERIES}).",
    )
    p.add_argument(
        "--height",
        type=int,
        default=DEFAULT_HEIGHT,
        help=f"The map's height in the window, in px (default {DEFAULT_HEIGHT}).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.tolerance < COARSE_SLACK:
        # A target's Trial starts where the character was read; a minimap-only
        # read arrives there only when its whole canvas pixel is within tolerance.
        sys.stderr.write(f"error: --tolerance must be at least {COARSE_SLACK:.1f}.\n")
        return 2
    if args.budget <= 0 or args.series < 1:
        sys.stderr.write("error: --budget must be positive and --series at least 1.\n")
        return 2
    try:
        profile = load(pick_profile(args.profile, available()))
        settings = dict(profile.main.settings)
        if args.map:
            settings["map"] = args.map
        try:
            binds = controller.key_binds(profile.main.ign)
        except AssertionError as error:
            raise ProfileError(f"configs/keybindings.ini: {error}") from error
        clash = colliding_keys(binds)
        if clash:
            raise ProfileError(
                f"The playground's key(s) {', '.join(clash)} are also your jump or "
                "Teleport key: the bot's keys could trigger them. Rebind in the game "
                "and in configs/keybindings.ini."
            )
        discord = check_configs()
        asyncio.run(_session(profile.main.ign, settings, args, discord=discord))
    except (ProfileError, StartupRefused) as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    # Through the package path, so the bot and the window pickle by their
    # importable names (`toolkit.movement_playground.*`), not `__main__`.
    from toolkit.movement_playground import main as _main

    raise SystemExit(_main())
