"""
The launch window: the maintainer draws, picks or saves a Hunting Area on the
whole map, with the character and the other players live (#571, spec section 8).

    python -m maple.launchers.hunting_area_window "Victoria Road: Ellinia"
    python -m maple.launchers.hunting_area_window 100000000

**It sends no key and no mouse event, ever.** It reads the client's pixels as a
Session does (`botting.screen`), reads where the client's window is to put its own
beside it, and draws in an OpenCV window. The only keys it reads are the ones
pressed in that window. The standalone entry point needs no Session: with the
client running it shows the markers live, without it the map alone. No frame is
saved.

**Layers.** `HuntingAreaPicker` is the window's logic and calls no `cv2`: it takes
window pixels and key codes and holds the rectangle, the typed name and the
message. `choose_hunting_area` is the OpenCV shell around it.

**The suggested rectangle** is drawn once, from the first position read, and
stays where it was: it does not follow the character. Drawing, taking a saved
area or saving replaces it.

| Input | Effect |
| --- | --- |
| Drag | Draw a new rectangle |
| `1` to `9` | Take that saved area, in name order |
| `S`, a name, Enter | Save the rectangle under that name |
| Enter | Hunt this rectangle |
| Esc | Give up |
"""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

import cv2
import numpy as np
import win32gui
from numpy.typing import NDArray

from botting.utilities import Box
from game_data.sprites import Sprite
from maple.model.world import HuntingArea, MinimapTransform, WorldMap
from maple.model.world.hunting_area import (
    HUNTING_AREAS,
    NAME,
    Stretch,
    save_area,
    saved_areas,
)

if TYPE_CHECKING:
    from maple.screen.minimap import MinimapView

MAX_WINDOW: Final = (1200, 800)
"""The most the window may measure, in px: width, height."""

MIN_WINDOW: Final = (520, 360)
"""The least: a small canvas is padded to this so the text fits."""

REFRESH: Final = 0.1
"""Seconds between two reads of what is live."""

SUGGEST_SIDE: Final = 500
"""Virtual px each side of the feet the suggested rectangle reaches."""
SUGGEST_ABOVE: Final = 250
SUGGEST_BELOW: Final = 100

ESC: Final = 27
ENTER: Final = 13
BACKSPACE: Final = 8
GAP: Final = 8
"""Px between the client's window and ours."""

TITLE: Final = "Hunting Area (sends no keys)"

type Point = tuple[float, float]


class NoDisplay(RuntimeError):
    """No window can be opened here: there is no display to draw on."""


class LiveReading(NamedTuple):
    """
    What is read from the client now, in virtual px; each may be `None` when it
    could not be read.

    :ivar character: Where the character's feet are.
    :ivar others: Where the other players' markers are.
    :ivar shown: The part of the map the client's minimap shows.
    """

    character: Point | None = None
    others: Sequence[Point] | None = None
    shown: Box | None = None


def live_reading(view: MinimapView | None, transform: MinimapTransform) -> LiveReading:
    """
    What the window shows live, from a minimap read with the `another` markers
    asked for: the character's feet, the other players' markers and the part of
    the map shown, in virtual px. Nothing of it with no view; no character and
    no others when the minimap places no position.
    """
    from maple.screen.minimap import FEET_ROWS, shown_in_virtual

    if view is None:
        return LiveReading()
    feet = view.self_position.value
    return LiveReading(
        character=(
            None
            if feet is None
            else transform.to_virtual((feet[0], feet[1] + FEET_ROWS))
        ),
        others=None
        if feet is None
        else [transform.to_virtual(p) for p in view.markers.get("another", ())],
        shown=None if view.shown is None else shown_in_virtual(view.shown, transform),
    )


def enlargement(canvas: tuple[int, int]) -> int:
    """
    The largest whole factor that keeps the canvas, enlarged, within
    `MAX_WINDOW`; at least 1.

    :param canvas: Its width and height, in px.
    """
    width, height = canvas
    return max(1, min(MAX_WINDOW[0] // width, MAX_WINDOW[1] // height))


def suggested_rectangle(feet: Point | None, world_map: WorldMap) -> HuntingArea | None:
    """
    The rectangle around the feet, clipped to the map's bounds; `None` with no
    position.
    """
    if feet is None:
        return None
    bounds = world_map.bounds
    x, y = feet
    return HuntingArea(
        left=max(round(x - SUGGEST_SIDE), bounds.left),
        top=max(round(y - SUGGEST_ABOVE), bounds.top),
        right=min(round(x + SUGGEST_SIDE), bounds.right),
        bottom=min(round(y + SUGGEST_BELOW), bounds.bottom),
    )


class HuntingAreaPicker:
    """
    The launch window's state, with no window: where the rectangle is, which
    saved areas there are, the name being typed, and what to tell the maintainer.

    :ivar rectangle: The rectangle now, `None` before one is suggested or drawn.
    :ivar typing: The name being typed; `None` when none is.
    :ivar finished: Whether the window is to close.
    :ivar result: What the window returns: set by Enter on a rectangle that holds a
        stretch; `None` when it is given up.
    """

    def __init__(
        self,
        world_map: WorldMap,
        canvas: tuple[int, int],
        folder: Path = HUNTING_AREAS,
        factor: int | None = None,
    ) -> None:
        """
        :param canvas: The minimap canvas's width and height, in px.
        :param factor: How many window px one canvas px takes; `enlargement`'s
            by default.
        :raises ValueError: The map has no minimap transform.
        """
        if world_map.minimap is None:
            raise ValueError(f"map {world_map.id} has no minimap to draw it on")
        self.world_map = world_map
        self.folder = folder
        self.factor = enlargement(canvas) if factor is None else factor
        self.rectangle: HuntingArea | None = None
        self.typing: str | None = None
        self.finished = False
        self.result: HuntingArea | None = None
        self.live = LiveReading()
        self.saved = saved_areas(world_map.id, folder)
        self._transform = world_map.minimap
        self._message = ""
        self._settled = False  # a rectangle drawn, taken or suggested
        self._stretches: tuple[Stretch, ...] | None = None

    # --- reading ---------------------------------------------------------------

    @property
    def names(self) -> tuple[str, ...]:
        """The saved areas' names, in order; the first nine have the keys 1 to 9."""
        return tuple(self.saved)

    @property
    def stretches(self) -> tuple[Stretch, ...]:
        """What the rectangle holds of the map's Platforms; empty with none."""
        if self.rectangle is None:
            return ()
        if self._stretches is None:
            self._stretches = self.rectangle.stretches(self.world_map)
        return self._stretches

    @property
    def message(self) -> str:
        """What to tell the maintainer now; empty when there is nothing."""
        return self._message or self._coverage()

    def to_virtual(self, window: tuple[int, int]) -> tuple[int, int]:
        """A point of the window, in whole virtual px."""
        x, y = self._transform.to_virtual(
            (window[0] / self.factor, window[1] / self.factor)
        )
        return round(x), round(y)

    def to_window(self, virtual: Point) -> tuple[int, int]:
        """A virtual position, in window px."""
        x, y = self._transform.to_canvas(virtual)
        return round(x * self.factor), round(y * self.factor)

    # --- input -----------------------------------------------------------------

    def update(self, live: LiveReading) -> None:
        """Take what is read now; the first position read suggests a rectangle."""
        self.live = live
        if not self._settled and self.rectangle is None:
            suggestion = suggested_rectangle(live.character, self.world_map)
            if suggestion is not None:
                self._set(suggestion)
                self._settled = True

    def drag(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        """
        A drag from `start` to `end`, in window px: the rectangle between them,
        whichever corner it starts from. A drag that did not move, or one made
        while a name is typed, changes nothing.
        """
        if self.typing is not None or start == end:
            return
        self._message = ""
        (x1, y1), (x2, y2) = self.to_virtual(start), self.to_virtual(end)
        self._set(HuntingArea(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        self._settled = True

    def press(self, key: int) -> None:
        """A key pressed in the window, as `cv2.waitKey` gives it."""
        self._message = ""
        if self.typing is not None:
            self._type(key)
        elif key == ESC:
            self.finished = True
        elif key == ENTER:
            self._hunt()
        elif key in (ord("s"), ord("S")):
            self._start_name()
        elif ord("1") <= key <= ord("9"):
            self._take(key - ord("1"))

    # --- what a key does -------------------------------------------------------

    def _type(self, key: int) -> None:
        assert self.typing is not None
        if key == ESC:
            self.typing = None
        elif key == ENTER:
            self._save(self.typing)
        elif key == BACKSPACE:
            self.typing = self.typing[:-1]
        elif 32 <= key < 127:
            self.typing += chr(key).lower()

    def _start_name(self) -> None:
        if self.rectangle is None:
            self._message = "draw a rectangle first"
        else:
            self.typing = ""

    def _save(self, name: str) -> None:
        assert self.rectangle is not None
        if NAME.fullmatch(name) is None:
            self._message = (
                f"a name is 1 to 24 characters of a-z, 0-9 and _: {name!r} is not one"
            )
            return
        area = HuntingArea(
            self.rectangle.left,
            self.rectangle.top,
            self.rectangle.right,
            self.rectangle.bottom,
            name=name,
        )
        if not area.stretches(self.world_map):
            self._message = _NO_STRETCH
            return
        save_area(self.world_map, area, self.folder)
        self.saved = saved_areas(self.world_map.id, self.folder)
        self.typing = None
        self._set(area)
        self._message = f"saved as {name}"

    def _take(self, index: int) -> None:
        if index >= len(self.names):
            self._message = f"no saved area {index + 1}"
            return
        self._set(self.saved[self.names[index]])
        self._settled = True

    def _hunt(self) -> None:
        if self.rectangle is None:
            self._message = "draw a rectangle first"
        elif not self.stretches:
            self._message = _NO_STRETCH
        else:
            self.result = self.rectangle
            self.finished = True

    def _set(self, area: HuntingArea) -> None:
        self.rectangle = area
        self._stretches = None

    def _coverage(self) -> str:
        shown, area = self.live.shown, self.rectangle
        if shown is None or area is None:
            return ""
        if area.right - area.left > shown.right - shown.left or (
            area.bottom - area.top > shown.bottom - shown.top
        ):
            return (
                "larger than what the minimap shows: other players are seen "
                "in part of it only"
            )
        return ""


_NO_STRETCH: Final = "this rectangle holds no Platform: draw it around one"


# --- placing the window --------------------------------------------------------


def placed_beside(
    client: Box | None, size: tuple[int, int], screen: tuple[int, int], work: Box
) -> tuple[int, int]:
    """
    Where to put a window of `size`: right of the client's area when it fits on
    the screen there, else left of it, else the work area's top-left. With no
    client, the work area's top-left.
    """
    corner = (work.left, work.top)
    if client is None:
        return corner
    top = min(max(client.top, work.top), max(work.top, work.bottom - size[1]))
    if client.right + GAP + size[0] <= screen[0]:
        return client.right + GAP, top
    if client.left - GAP - size[0] >= 0:
        return client.left - GAP - size[0], top
    return corner


# --- drawing -------------------------------------------------------------------

_BLUE = (255, 160, 60)
_GREEN = (80, 220, 80)
_RED = (60, 60, 240)
_YELLOW = (60, 220, 240)
_GREY = (150, 150, 150)
_WHITE = (240, 240, 240)

type Image = NDArray[np.uint8]


def _base(canvas: Sprite, factor: int) -> Image:
    """The canvas over a dark ground, enlarged, padded to `MIN_WINDOW`."""
    rgba = canvas.rgba
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255
    ground = np.full(rgba.shape[:2] + (3,), 30, np.float32)
    bgr = rgba[:, :, 2::-1].astype(np.float32) * alpha + ground * (1 - alpha)
    image = cv2.resize(
        bgr.astype(np.uint8),
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_NEAREST,
    )
    height, width = image.shape[:2]
    pad = np.full(
        (max(height, MIN_WINDOW[1]), max(width, MIN_WINDOW[0]), 3), 30, np.uint8
    )
    pad[:height, :width] = image
    return pad


def draw(picker: HuntingAreaPicker, base: Image) -> Image:
    """The window's picture: the map with everything over it."""
    image = base.copy()
    where = picker.to_window
    for platform in picker.world_map.platforms:
        for f in platform.footholds:
            cv2.line(image, where((f.x1, f.y1)), where((f.x2, f.y2)), _GREY, 1)
    for stretch in picker.stretches:
        xs = [stretch.left, stretch.right]
        xs[1:1] = sorted(
            x
            for f in stretch.platform.footholds
            for x in (f.x1, f.x2)
            if stretch.left < x < stretch.right
        )
        line = [(x, stretch.y_at(x)) for x in xs]
        points = np.array([where((x, y)) for x, y in line if y is not None], np.int32)
        cv2.polylines(image, [points], False, _YELLOW, 3)
    if picker.live.shown is not None:
        shown = picker.live.shown
        cv2.rectangle(
            image,
            where((shown.left, shown.top)),
            where((shown.right, shown.bottom)),
            _BLUE,
            1,
        )
    if picker.rectangle is not None:
        r = picker.rectangle
        cv2.rectangle(
            image, where((r.left, r.top)), where((r.right, r.bottom)), _WHITE, 2
        )
    for other in picker.live.others or ():
        cv2.circle(image, where(other), 5, _RED, -1)
    if picker.live.character is not None:
        cv2.circle(image, where(picker.live.character), 5, _GREEN, -1)
        cv2.circle(image, where(picker.live.character), 7, _WHITE, 1)
    _text(image, _lines(picker))
    return image


def _lines(picker: HuntingAreaPicker) -> list[str]:
    lines = ["drag: draw  1-9: saved  S: save  Enter: hunt  Esc: give up"]
    for number, name in enumerate(picker.names, start=1):
        key = str(number) if number <= 9 else "-"
        lines.append(f"  {key} {name}")
    if picker.typing is not None:
        lines.append(f"name: {picker.typing}_   (Enter saves, Esc drops it)")
    if picker.message:
        lines.append(picker.message)
    return lines


def _text(image: Image, lines: list[str]) -> None:
    height = 16 * len(lines) + 6
    width = min(image.shape[1], 470)
    shade = image[:height, :width].copy()
    image[:height, :width] = (shade * 0.35).astype(np.uint8)
    for row, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (6, 16 * (row + 1)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            _WHITE,
            1,
            cv2.LINE_AA,
        )


# --- the window ----------------------------------------------------------------


def choose_hunting_area(
    world_map: WorldMap,
    canvas: Sprite,
    folder: Path,
    handle: int | None,
    read: Callable[[], LiveReading],
) -> HuntingArea | None:
    """
    Open the window and wait for the maintainer.

    :param canvas: The map's own minimap canvas (`MinimapReader.canvas`).
    :param folder: Where the saved areas are.
    :param handle: The client's window handle, to place the window beside it;
        `None` with no client.
    :param read: What is read from the client now; called about ten times a
        second, and may return `None` for any part.
    :returns: The area chosen, or `None` when the maintainer gives up or closes
        the window.
    :raises NoDisplay: No window can be opened; nothing waits.
    """
    height, width = canvas.rgba.shape[:2]
    picker = HuntingAreaPicker(world_map, (width, height), folder)
    base = _base(canvas, picker.factor)
    drag: list[tuple[int, int]] = []

    def mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            drag[:] = [(x, y)]
        elif drag and event in (cv2.EVENT_MOUSEMOVE, cv2.EVENT_LBUTTONUP):
            picker.drag(drag[0], (x, y))
            if event == cv2.EVENT_LBUTTONUP:
                drag.clear()

    try:
        _check_display()
        cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)
    except cv2.error as error:
        raise NoDisplay(f"no window can be opened here: {error}") from error
    try:
        cv2.setMouseCallback(TITLE, mouse)
        _place(base.shape[1], base.shape[0], handle)
        last = 0.0
        while not picker.finished:
            if time.monotonic() - last >= REFRESH:
                picker.update(read())
                last = time.monotonic()
            cv2.imshow(TITLE, draw(picker, base))
            key = cv2.waitKey(30) & 0xFF
            if key != 0xFF:
                picker.press(key)
            if cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cv2.destroyWindow(TITLE)
    return picker.result


def _check_display() -> None:
    from maple.window_placement import screen_size

    try:
        width, height = screen_size()
    except win32gui.error as error:
        raise NoDisplay(f"the screen's size can't be read: {error}") from error
    if width <= 0 or height <= 0:
        raise NoDisplay("there is no display")


def _place(width: int, height: int, handle: int | None) -> None:
    from maple.window_placement import client_rect, screen_size, work_area

    client = None
    if handle is not None:
        try:
            client = client_rect(handle)
        except win32gui.error:  # the client closed: place it with no client
            client = None
    x, y = placed_beside(client, (width, height), screen_size(), work_area())
    cv2.moveWindow(TITLE, x, y)


# --- the standalone entry point ------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m maple.launchers.hunting_area_window",
        description="Draw, pick or save a Hunting Area on a map. Sends no key.",
    )
    parser.add_argument("map", help="the map's game name or id, as the profile's `map`")
    args = parser.parse_args(argv)

    from botting.screen import MultipleWindows, WindowNotFound, frame_source
    from maple.bots.map_setting import resolve_map_id
    from maple.launchers.profile import ProfileError
    from maple.screen.client import find_client
    from maple.screen.locator import FrameCheck
    from maple.screen.minimap import MINIMAP, MinimapReader
    from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites

    text: str = args.map.strip()
    try:
        map_id = resolve_map_id(int(text) if text.isdigit() else text)
    except ProfileError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    if map_id is None:
        sys.stderr.write("name a map: `auto` needs a running Session\n")
        return 2
    world_map = WorldMap.load(map_id)
    transform = world_map.minimap
    if transform is None:
        sys.stderr.write(f"map {map_id} has no minimap to draw it on\n")
        return 2
    sprites = load_reader_sprites(
        [FRAME_CHECK, MINIMAP], Profile(job="", map_id=map_id)
    )
    reader = MinimapReader(sprites, FrameCheck(sprites), map_id=map_id)
    assert reader.canvas is not None
    try:
        handle: int | None = find_client()
    except WindowNotFound, MultipleWindows:
        handle = None

    def read() -> LiveReading:
        if handle is None:
            return LiveReading()
        frame = frame_source().grab(handle)
        if not frame.ok:
            return LiveReading()
        return live_reading(reader.read(frame, markers=("another",)).value, transform)

    try:
        area = choose_hunting_area(
            world_map, reader.canvas, HUNTING_AREAS, handle, read
        )
    except NoDisplay as error:
        sys.stderr.write(f"{error}\n")
        return 3
    if area is None:
        sys.stdout.write("no area chosen\n")
        return 1
    sys.stdout.write(f"{area}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
