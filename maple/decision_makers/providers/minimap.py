"""
The minimap: its reading, whether it is shown, where it is, and the character's
virtual position read from it.

`MinimapProvider` holds what `MinimapAttributesMixin._create_minimap_attributes`
set up, and is built once per Bot: by assembly when a DecisionMaker reads one of
its keys, or when an unported DecisionMaker's mixin asks `BotData` for it.

Two helpers are shared with DecisionMakers that need them:

- `MinimapRecovery` makes the minimap place the character again. The Provider
  holds one as `POSITION`'s error handler; `CheckStillInMap` holds its own.
- `PositionReader` reads the virtual position, and holds while the minimap's
  marker is unplaced. The Provider holds one for `POSITION`; a DecisionMaker
  that reads a position itself, with no error handler (`TrialRunner`'s
  samples), holds its own.
"""

import logging
import multiprocessing.connection
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import win32gui

from botting import PARENT_LOG, controller
from botting.core import (
    HANDLE,
    ActionRequest,
    BotData,
    Key,
    Provider,
    ProxyFactory,
    StartupRefused,
)
from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from maple.actions import ensure_minimap_displayed
from maple.decision_makers.readings import HeldReading
from maple.screen.minimap import MinimapReader, MinimapState, MinimapView
from maple.screen.position import Fusion, PositionFusion, VirtualPosition
from maple.telemetry_events import POSITION_READ, PositionReadPayload

from .client import FRAME
from .map import POSITION_FUSION
from .screen_readers import MINIMAP_READER

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

UNPLACED_LIMIT = 120.0
"""
Wall seconds the minimap may stay shown without placing the character's
marker before the bot stops holding (#502). Until then the position is
`UNSURE`, so no Path is planned and no movement key is sent; past it,
`POSITION`'s error handler gets one last try (moving the cursor off the
minimap, re-showing it, 5 checks: about 10 s more), and the bot fails if that
can't place it either.

Why 120 s: movement recovery reports an unsure position after 30 s
(`RecoveryThresholds.unsure_window`), so the hold is logged and reported well
before it ends. What it waits out passes in seconds: a player or a window over
the marker, the character walking out of a corner where too little of it is
drawn. A character that can't be placed for two minutes is standing still in
front of anyone watching, and a bot that can't see itself shouldn't go on.
"""


class MinimapProvider(Provider):
    """
    Serves the minimap's reading, whether it is shown, its box on the client,
    and the character's virtual position.

    `setup()` shows the minimap expanded (`ensure_minimap_displayed`), then
    registers the four keys, in that order: the reading, whether it is shown
    and its box are read at once; the position waits for its first reader.
    A position the minimap can't give goes to `MinimapRecovery`.
    """

    needs = (HANDLE, FRAME, MINIMAP_READER, POSITION_FUSION)

    #: Seconds a reading, a box and a position are served before a read
    #: refreshes them.
    REFRESH = 0.1
    #: Seconds the minimap key may be pressed for to show the minimap.
    TIME_LIMIT = 7.5

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        self._shown = HeldReading[MinimapView, bool](
            self,
            "minimap shown",
            lambda view: view.state is MinimapState.EXPANDED,
            False,
            absent=lambda: False,
        )
        self._bounds = HeldReading[MinimapView, Box | None](
            self, "minimap bounds", lambda view: view.bounds, None
        )
        self._position = PositionReader(
            self,
            self.emit,
            fusion=lambda: self.read(POSITION_FUSION),
            minimap=lambda: self.read(MINIMAP_READING),
            frame=lambda: self.read(FRAME),
        )
        self._recovery = MinimapRecovery(self, self.proxies)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no minimap reader, which a MapleBot
            always has.
        """
        identifier = f"{self} Initial Setup"
        ensure_minimap_displayed(
            identifier,
            self.read(HANDLE),
            self.data.ign,
            self.pipe,
            self._reader(),
            self.proxies.instance(identifier, "Condition"),
            self.TIME_LIMIT,
        )
        self.register(MINIMAP_READING, self._read, threshold=self.REFRESH)
        self.register(MINIMAP_SHOWN, lambda: self._shown(self.read(MINIMAP_READING)))
        # Refreshed with the reading it comes from, so a client resized
        # mid-session moves it too.
        self.register(
            MINIMAP_BOX,
            lambda: self._bounds(self.read(MINIMAP_READING)),
            threshold=self.REFRESH,
        )
        # Not read here: the first consumer to ask reads it, and its reads cost
        # a camera match each.
        self.register(
            POSITION,
            self._position,
            threshold=self.REFRESH,
            initial_value=Reading.unsure(0.0, "not read yet"),
            error_handler=self._recovery,
        )

    def _reader(self) -> MinimapReader:
        reader = self.read(MINIMAP_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no minimap reader: the Bot's sprites have no minimap."
            )
        return reader

    def _read(self) -> Reading[MinimapView]:
        return self._reader().read(self.read(FRAME))


#: The minimap, read from the latest frame.
MINIMAP_READING: Key[Reading[MinimapView]] = Key("minimap_reading", MinimapProvider)
#: Whether the minimap is read expanded: a minimised one shows no map, so no
#: position. Not on screen is an answer (False); covered or unsure keeps the last
#: answer (`HeldReading`). Refreshed only when asked to: it has no threshold.
MINIMAP_SHOWN: Key[bool] = Key(
    "minimap_shown", MinimapProvider, legacy_name="minimap_currently_displayed"
)
#: The whole minimap, frame included, in client pixels: the last one read, or
#: None before the first (`HeldReading`).
MINIMAP_BOX: Key[Box | None] = Key(
    "minimap_box", MinimapProvider, legacy_name="current_entire_minimap_box"
)
#: The character's position, in virtual px, for every DecisionMaker (#398):
#: `PositionReader`'s, with `MinimapRecovery` as its error handler.
POSITION: Key[Reading[VirtualPosition]] = Key(
    "position", MinimapProvider, legacy_name="current_position"
)


class _Holder(Protocol):
    """Whoever holds a `MinimapRecovery`: a DecisionMaker, or the Provider."""

    data: BotData
    pipe: multiprocessing.connection.Connection

    def read[T](self, key: Key[T]) -> T: ...

    def refresh[T](self, key: Key[T]) -> T: ...

    def send(self, request: ActionRequest) -> None: ...


class MinimapRecovery:
    """
    Makes the minimap place the character again: moves the cursor off the
    minimap, shows the minimap expanded, and checks that it places the
    character, up to `ATTEMPTS` times. It blocks the Bot, and so its Engine,
    until it is done, uninterrupted by other tasks.

    It reads through its holder, whose `reads` (or `needs`) must declare every
    key in `reads`, and sends through it: its Actions are its holder's.
    """

    #: The keys it reads, which its holder declares.
    reads = (HANDLE, MINIMAP_READER, FRAME, MINIMAP_READING, MINIMAP_SHOWN, MINIMAP_BOX)
    #: How many times it shows the minimap before it gives up and raises.
    ATTEMPTS = 5

    def __init__(self, holder: _Holder, proxies: ProxyFactory) -> None:
        """
        :param holder: Who reads, sends, and names the Actions.
        :param proxies: Its holder's Bot's proxies, for the minimap's Condition.
        """
        self.holder = holder
        self.proxies = proxies

    def __call__(self) -> None:
        """
        :raises Exception: the minimap still doesn't place the character after
            `ATTEMPTS` tries: the last check's error.
        """
        holder = self.holder
        identifier = f"{holder}.current_position Error Handler"
        logger.warning("%s Attempt", identifier)
        condition = self.proxies.instance(identifier, "Condition")
        attempt = 0
        while True:
            # The cursor goes first: resting on a frame piece, it makes the minimap
            # read COVERED, and `ensure_minimap_displayed` would press the toggle
            # on an expanded minimap. The move runs during the pause below.
            self.move_cursor_off_minimap(identifier)
            time.sleep(1.5)
            reader = holder.read(MINIMAP_READER)
            assert reader is not None, "MinimapProvider refuses a Bot without one"
            ensure_minimap_displayed(
                identifier,
                holder.read(HANDLE),
                holder.data.ign,
                holder.pipe,
                reader,
                condition,
                MinimapProvider.TIME_LIMIT,
            )
            logger.info("Minimap fully displayed confirmed")
            try:
                holder.refresh(FRAME)
                minimap_position(holder.refresh(MINIMAP_READING))
                break
            except Exception:
                attempt += 1
                logger.error("%s Attempt %s failed", identifier, attempt)
                if attempt >= self.ATTEMPTS:
                    raise

        for key in (FRAME, MINIMAP_READING, MINIMAP_SHOWN, MINIMAP_BOX):
            holder.refresh(key)

    def move_cursor_off_minimap(self, identifier: str) -> None:
        """
        Moves the cursor to a random point of the client that is not on the
        minimap: off its box when one was read, else off the client's top-left
        500 px square.
        :param identifier: The mouse move's Action name.
        """
        holder = self.holder
        box = holder.read(MINIMAP_BOX)
        region_to_avoid = (
            box if box is not None else Box(left=0, right=500, top=0, bottom=500)
        )
        # Both are in client pixels, which is what `controller.mouse_move` takes.
        handle = holder.read(HANDLE)
        _, _, width, height = win32gui.GetClientRect(handle)
        client_box = Box(left=0, right=width, top=0, bottom=height)
        while True:
            x, y = client_box.random()
            if (x, y) not in region_to_avoid:
                break

        holder.send(
            ActionRequest(
                identifier,
                controller.mouse_move,
                holder.data.ign,
                args=(handle, (x, y)),
                cancels_itself=True,
            )
        )


def minimap_position(reading: Reading[MinimapView]) -> tuple[int, int]:
    """
    The minimap marker's canvas pixel: whether the minimap places the character
    at all, which is what `MinimapRecovery` checks after each attempt. No
    DecisionMaker positions itself by it since #398: `POSITION` is the
    position, in virtual px.

    :raises ValueError: The minimap wasn't read, or the position wasn't (the
        map's canvas not found, or its marker covered).
    """
    if reading.value is None:
        raise ValueError(
            f"minimap {reading.status.value}: {reading.detail or 'no detail'}"
        )
    position = reading.value.self_position
    if position.value is None:
        raise ValueError(f"position {position.status.value}: {position.detail}")
    return position.value


class PositionReader:
    """
    The character's virtual position (`PositionFusion`), from the minimap
    reading and the current frame. Every read is recorded (`position.read`),
    unsure ones included.

    **Who handles an unsure position** (#396). When the minimap gave no
    position, this raises, and `MinimapRecovery` makes the minimap readable
    again. When the minimap places the character, fusion places it too:
    `coarse` where the play area doesn't (the reads disagree, or two characters
    stand where the minimap puts ours: #529), with why in the detail. A
    consumer that gets an `UNSURE` reading holds until a read places the
    character (`MovementsMixin` plans no Path, the rotation keeps its target).
    A long streak of them is reported by movement recovery (#398).

    **A shown minimap that doesn't place the marker holds too** (#502). Its
    position is `COVERED` (too little of the marker drawn): re-showing the
    minimap can't fix that, so the `UNSURE` reading is returned, the cause is
    logged once, and every read tries again. Only once that has lasted
    `UNPLACED_LIMIT` does this raise, for the error handler's last try.
    """

    def __init__(
        self,
        owner: object,
        emit: Callable[[str, Mapping[str, Any]], None],
        *,
        fusion: Callable[[], PositionFusion | None],
        minimap: Callable[[], Reading[MinimapView]],
        frame: Callable[[], Frame],
    ) -> None:
        """
        :param owner: Who reads, in the log lines.
        :param emit: Emits the `position.read` record.
        :param fusion: The map's `PositionFusion`, None when it has none.
        :param minimap: The minimap reading.
        :param frame: The frame it was read from.
        """
        self._owner = owner
        self._emit = emit
        self._fusion = fusion
        self._minimap = minimap
        self._frame = frame
        #: When the minimap, shown, stopped placing the character's marker.
        self._unplaced_since: float | None = None

    def __call__(self) -> Reading[VirtualPosition]:
        """
        :raises ValueError: The minimap gave no position (not shown, not read,
            its canvas not found, or its marker unplaced for `UNPLACED_LIMIT`),
            or the bot has no position fusion (no map, or no frame check), which
            hands over to `MinimapRecovery`.
        """
        fusion = self._fusion()
        if fusion is None:
            raise ValueError("no position fusion: the bot's map isn't known")
        minimap = self._minimap()
        result = fusion.read(self._frame(), minimap)
        self._emit(POSITION_READ, position_read_payload(result))
        position = result.position
        if result.minimap is not None:
            self._unplaced_since = None
        elif _marker_unplaced(minimap):
            return self._hold_unplaced(position)
        elif position.value is None:
            raise ValueError(f"position {position.status.value}: {position.detail}")
        return position

    def _hold_unplaced(
        self, position: Reading[VirtualPosition]
    ) -> Reading[VirtualPosition]:
        """`position`, the minimap shown but its marker unplaced; it raises
        once that has lasted `UNPLACED_LIMIT`."""
        now = time.monotonic()
        if self._unplaced_since is None:
            self._unplaced_since = now
            logger.warning(
                "%s holds: %s. It gives up if this lasts %.0f s.",
                self._owner,
                position.detail,
                UNPLACED_LIMIT,
            )
        elif now - self._unplaced_since >= UNPLACED_LIMIT:
            self._unplaced_since = None
            raise ValueError(
                f"position {position.status.value} for {UNPLACED_LIMIT:.0f} s: "
                f"{position.detail}"
            )
        return position


def _marker_unplaced(minimap: Reading[MinimapView]) -> bool:
    """Whether the minimap is read, shown with its map found, and only the
    character's marker isn't placed (`COVERED`)."""
    view = minimap.value
    return (
        view is not None
        and view.state is MinimapState.EXPANDED
        and view.self_position.status is Status.COVERED
    )


def position_read_payload(fusion: Fusion) -> PositionReadPayload:
    """`position.read`'s payload, from a read of the position."""
    value = fusion.position.value
    camera = fusion.camera
    minimap = fusion.minimap
    return {
        "status": fusion.position.status.value,
        "source": None if value is None else value.source.value,
        "x": None if value is None else round(float(value.x), 1),
        "y": None if value is None else round(float(value.y), 1),
        "minimap_x": None if minimap is None else int(minimap[0]),
        "minimap_y": None if minimap is None else int(minimap[1]),
        "camera_x": None if camera is None else int(camera.x),
        "camera_y": None if camera is None else int(camera.y),
        "found": len(fusion.sightings),
        "near": fusion.near,
        "by_tag": fusion.by_tag,
        "own_elsewhere": fusion.own_elsewhere,
        "detail": fusion.position.detail,
    }
