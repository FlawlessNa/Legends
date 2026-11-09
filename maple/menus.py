"""
Driving the client's Game Menu and Options window: open the Game Menu, go to
Options, and set the resolution (#352).

Every step is found on the screen, from the client's own `UI.wz` sprites, and
checked on a fresh frame before the next one:

- **The Game Menu** (`Escape`) is `UI/StatusBar.img/submenu`: its title canvas,
  and its `button:GameOpt` placed by that canvas's origin.
- **The Options window** is `UI/Options.img`: its five tabs (Graphics, Sound,
  Game, Social, Controller), each `enabled` (selected) or `disabled`, and its
  `button:OK` (Confirm). Every position is the window's point plus a sprite's
  origin, so nothing depends on the client's size: the window is centred in the
  client, and moves when the client resizes.
- **The resolution dropdown** is `graphic/combo:resolution`, whose `lt` and `rb`
  vectors place it in the window. Its list is drawn by the client, not from
  sprites: rows of `backColor` with the selected one in `backFocusedColor` (both
  from that node). The list is found by scanning a column for those colours, and
  its row pitch is its height over its row count, so no row height is measured
  on one size.

**The UI's scale.** At most sizes the client draws its UI at 1:1. At 2560x1440
it draws everything at 1280x720 and doubles each pixel, whatever the UI Size
(#412). The sprites then match exactly on every second pixel, so the steps run
on that half-size frame (`at_scale`) and their clicks are doubled back
(`ScaledClient`). The scale is found on the screen (`find_scale`, from the
status bar), never from the size. Closing the menus finds it again on each
frame, since Confirm may have changed it, and looks at every scale when the
status bar can't be found.

Input goes through a `Client`, which the probe implements with its guarded
gestures (each releases every key). On any failure the functions close the menus
with `Escape` before they raise, so the game is not left on an open dialog.
After Confirm, and on a failure, the client is asked to `fit` its client area
on the primary monitor, since a resize can leave part of it off the screen.

This is a scripted sequence, which the probe's intent (#331) left to Bots. It is
here because the maintainer asked agents to stop rediscovering this menu.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, match_best, matches_at

from .screen.locator import FrameCheck, Part
from .screen.sprites import FRAME_CHECK, Declaration, ReaderSprites

# The windowed sizes, in the order the dropdown lists them. The list then gives
# the same sizes again, in full screen, which are refused.
WINDOWED_SIZES: tuple[tuple[int, int], ...] = (
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1366, 768),
    (1920, 1080),
    (1920, 1200),
    (2560, 1440),
)
LIST_ROWS = 2 * len(WINDOWED_SIZES)

# The scales the client draws its UI at: 1:1, and each pixel doubled (2560x1440).
UI_SCALES = (1, 2)

_MENU = "UI/StatusBar.img/submenu"
MENU_TITLE = f"{_MENU}/canvas:menu"
_GAME_OPTION = f"{_MENU}/menu/button:GameOpt"
GAME_OPTION_STATES = tuple(
    f"{_GAME_OPTION}/{state}/0" for state in ("normal", "mouseOver", "pressed")
)

_OPTIONS = "UI/Options.img"
TAB_COUNT = 5
GRAPHICS_TAB = 0
TABS_ENABLED = tuple(f"{_OPTIONS}/tab/enabled/{i}" for i in range(TAB_COUNT))
TABS_DISABLED = tuple(f"{_OPTIONS}/tab/disabled/{i}" for i in range(TAB_COUNT))
SEARCHED_TABS = (TABS_DISABLED[1], TABS_DISABLED[3], TABS_DISABLED[4])
CONFIRM = f"{_OPTIONS}/button:OK/normal/0"
_RESOLUTION = f"{_OPTIONS}/graphic/combo:resolution"
RESOLUTION_LT = f"{_RESOLUTION}/lt"
RESOLUTION_RB = f"{_RESOLUTION}/rb"

# The Key Bindings window swallows Escape, so it is refused rather than closed.
KEY_BINDINGS_TABS = tuple(
    f"UI/KeyBindings.img/tab:kind/{state}/{i}"
    for state in ("selected", "normal")
    for i in (0, 1)
)

MENUS = Declaration(
    "game menu",
    canvases=(
        MENU_TITLE,
        *GAME_OPTION_STATES,
        *TABS_ENABLED,
        *TABS_DISABLED,
        CONFIRM,
        *KEY_BINDINGS_TABS,
    ),
    vectors=(RESOLUTION_LT, RESOLUTION_RB),
)
"""The sprites these functions read; load with `FRAME_CHECK` in front."""

DECLARATIONS = (FRAME_CHECK, MENUS)

# `combo:resolution`'s `backColor` (-1118482) and `backFocusedColor` (-5922408),
# ARGB, as the BGR a frame holds. The store keeps only canvases and vectors in
# `ReaderSprites`, so they are copied here; a `client_files` test checks them.
LIST_BACK = (238, 238, 238)
LIST_FOCUSED = (152, 161, 165)
# The column the list is scanned in, from the combo's `lt`: inside its border
# (`boxPosX` 1) and left of its text (`textLeft` 6).
LIST_COLUMN = 4

# How long a step waits for the screen to show its result, polling a fresh frame.
STEP_TIMEOUT = 3.0
RESIZE_TIMEOUT = 8.0
POLL = 0.1
MAX_ESCAPES = 4


class Client(Protocol):
    """What the functions need of the client: frames, its size, and guarded input."""

    def grab(self) -> Frame:
        """A fresh frame, `ok` or not."""
        ...

    def size(self) -> tuple[int, int]:
        """The client area's size now, read from the window rather than a frame."""
        ...

    def fit(self) -> None:
        """
        Moves the window, when its client area isn't entirely on the primary
        monitor and could be, so that it is. Sends no input.
        """
        ...

    def press(self, key: str) -> None:
        """One guarded key press: keydown, keyup, every key released."""
        ...

    def click(self, x: int, y: int) -> None:
        """One guarded left click at client pixels."""
        ...

    def wait(self, seconds: float) -> None: ...


class MenuError(Exception):
    """A step didn't see what it expected. Says which step, and what it saw."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


# --- the UI's scale -------------------------------------------------------------


def at_scale(frame: Frame, scale: int) -> Frame:
    """
    `frame` as the client drew it before doubling its pixels `scale` times: every
    `scale`-th pixel, and the size divided by `scale`.
    """
    if scale == 1:
        return frame
    width, height = frame.client_size
    return replace(
        frame,
        pixels=np.ascontiguousarray(frame.pixels[::scale, ::scale]),
        client_size=(width // scale, height // scale),
    )


@dataclass(frozen=True, slots=True)
class NotYet:
    """What a `wait_for` check returns when the frame doesn't show it, and why."""

    why: str


def find_scale(check: FrameCheck, frame: Frame) -> int | NotYet:
    """The first of `UI_SCALES` the frame check passes at, or why none does."""
    if not frame.ok:
        return NotYet(f"the frame isn't the client's own pixels: {frame.reason}")
    for scale in UI_SCALES:
        if check.frame_usable(at_scale(frame, scale)) is None:
            return scale
    scales = " or ".join(f"{scale}:1" for scale in UI_SCALES)
    return NotYet(
        f"the status bar's gauge label isn't drawn at {scales}: is the status bar "
        'showing, uncovered, and the UI Size "Ideal Ratio"?'
    )


@dataclass(frozen=True, slots=True)
class ScaledClient:
    """
    `client` at the UI's scale: its frames through `at_scale`, and a click at a
    half-size pixel sent to the middle of the pixels the client doubled it to.
    """

    client: Client
    scale: int

    def grab(self) -> Frame:
        return at_scale(self.client.grab(), self.scale)

    def size(self) -> tuple[int, int]:
        return self.client.size()

    def fit(self) -> None:
        self.client.fit()

    def press(self, key: str) -> None:
        self.client.press(key)

    def click(self, x: int, y: int) -> None:
        half = self.scale // 2
        self.client.click(x * self.scale + half, y * self.scale + half)

    def wait(self, seconds: float) -> None:
        self.client.wait(seconds)


# --- finding things on a frame -------------------------------------------------


def _top_left(
    sprites: ReaderSprites, path: str, point: tuple[int, int]
) -> tuple[int, int]:
    dx, dy = Part(sprites.canvas(path)).offset
    return point[0] + dx, point[1] + dy


def _at(
    frame: Frame, sprites: ReaderSprites, path: str, point: tuple[int, int]
) -> bool:
    """Whether the canvas at `path` is drawn where `point` places it."""
    x, y = _top_left(sprites, path, point)
    return matches_at(frame.pixels, sprites.canvas(path).rgba, x, y)


def _point_of(
    frame: Frame, sprites: ReaderSprites, path: str
) -> tuple[int, int] | None:
    """The point the canvas at `path` is drawn from, wherever it best matches."""
    hit = match_best(frame.pixels, sprites.canvas(path).rgba)
    if hit is None:
        return None
    dx, dy = Part(sprites.canvas(path)).offset
    return hit.x - dx, hit.y - dy


def _centre(
    sprites: ReaderSprites, path: str, point: tuple[int, int]
) -> tuple[int, int]:
    x, y = _top_left(sprites, path, point)
    height, width = sprites.canvas(path).rgba.shape[:2]
    return x + width // 2, y + height // 2


@dataclass(frozen=True, slots=True)
class GameMenu:
    """
    The Game Menu, found.

    :ivar point: Where the client draws it from.
    :ivar game_option: The centre of its Game Option button, in client pixels.
    """

    point: tuple[int, int]
    game_option: tuple[int, int]


def find_game_menu(sprites: ReaderSprites, frame: Frame) -> GameMenu | None:
    """The Game Menu, when its title and its Game Option button are showing."""
    point = _point_of(frame, sprites, MENU_TITLE)
    if point is None:
        return None
    if not any(_at(frame, sprites, path, point) for path in GAME_OPTION_STATES):
        return None
    return GameMenu(point, _centre(sprites, GAME_OPTION_STATES[0], point))


@dataclass(frozen=True, slots=True)
class OptionsWindow:
    """
    The Options window, found.

    :ivar point: Where the client draws it from: its top-left corner.
    :ivar selected: The selected tab (0 is Graphics), or `None` when it can't be
        told, such as when the cursor covers more than one tab.
    """

    point: tuple[int, int]
    selected: int | None


def find_options(sprites: ReaderSprites, frame: Frame) -> OptionsWindow | None:
    """
    The Options window, when at least two of its tabs are where its point puts
    them. One tab may be covered, by the cursor that just clicked it.

    Searching a frame is the slow part, so only `SEARCHED_TABS` are searched for:
    with one tab selected and at most one covered, one of them always shows.
    """
    for path in SEARCHED_TABS:
        point = _point_of(frame, sprites, path)
        if point is None:
            continue
        enabled = [
            i for i, p in enumerate(TABS_ENABLED) if _at(frame, sprites, p, point)
        ]
        disabled = [
            i for i, p in enumerate(TABS_DISABLED) if _at(frame, sprites, p, point)
        ]
        if len(enabled) + len(disabled) < 2:
            continue
        if len(enabled) == 1:
            selected: int | None = enabled[0]
        elif not enabled and len(disabled) == TAB_COUNT - 1:
            selected = next(i for i in range(TAB_COUNT) if i not in disabled)
        else:
            selected = None
        return OptionsWindow(point, selected)
    return None


def key_bindings_open(sprites: ReaderSprites, frame: Frame) -> bool:
    """Whether the Key Bindings window shows: one of its two tabs is selected."""
    return any(
        _point_of(frame, sprites, path) is not None for path in KEY_BINDINGS_TABS[:2]
    )


@dataclass(frozen=True, slots=True)
class Combo:
    """The resolution dropdown's box, in client pixels."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def centre(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


def resolution_combo(sprites: ReaderSprites, window: OptionsWindow) -> Combo:
    (lx, ly), (rx, ry) = sprites.vector(RESOLUTION_LT), sprites.vector(RESOLUTION_RB)
    x, y = window.point
    return Combo(x + lx, y + ly, x + rx, y + ry)


@dataclass(frozen=True, slots=True)
class DropdownList:
    """
    The open resolution list.

    :ivar top: The first row's top, in client pixels.
    :ivar pitch: Each row's height.
    :ivar focused: The highlighted row, or `None` when none is.
    """

    top: int
    pitch: int
    focused: int | None

    def row_centre_y(self, row: int) -> int:
        return self.top + row * self.pitch + self.pitch // 2


def _runs(flags: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """The `[start, end)` of each run of True."""
    padded = np.concatenate(([False], flags, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True)]


def find_list(frame: Frame, combo: Combo) -> DropdownList | None:
    """
    The list under `combo`, when it is open: a run of list rows starting where
    the combo ends, `LIST_ROWS` rows tall.
    """
    x = combo.left + LIST_COLUMN
    if not 0 <= x < frame.pixels.shape[1]:
        return None
    column = frame.pixels[:, x].astype(np.int16)
    back = np.all(column == LIST_BACK, axis=1)
    focused = np.all(column == LIST_FOCUSED, axis=1)
    for start, end in _runs(back | focused):
        if not combo.top < start <= combo.bottom + 2:
            continue
        height = end - start
        pitch = round(height / LIST_ROWS)
        if pitch < 8 or abs(height - pitch * LIST_ROWS) > 1:
            return None
        bands = _runs(focused[start:end])
        row = bands[0][0] // pitch if len(bands) == 1 else None
        return DropdownList(start, pitch, row)
    return None


def _confirm_centre(sprites: ReaderSprites, window: OptionsWindow) -> tuple[int, int]:
    return _centre(sprites, CONFIRM, window.point)


# --- waiting -------------------------------------------------------------------


def wait_for[T](
    client: Client,
    step: str,
    found: Callable[[Frame], T | NotYet | None],
    expected: str,
    timeout: float | None = None,
) -> T:
    """
    Polls fresh frames until `found` returns something for an `ok` frame. A
    `NotYet` is nothing, with a reason the error repeats.

    :param timeout: Seconds; `STEP_TIMEOUT` when not given.
    :raises MenuError: It didn't within `timeout`, naming `step`, `expected` and
        why the last frame didn't show it, when that is known.
    """
    if timeout is None:
        timeout = STEP_TIMEOUT
    attempts = max(1, round(timeout / POLL))
    reason = ""
    for attempt in range(attempts):
        frame = client.grab()
        if frame.ok:
            result = found(frame)
            if isinstance(result, NotYet):
                reason = f" (the last frame: {result.why})"
            elif result is not None:
                return result
            else:
                reason = ""
        else:
            reason = f" (the last frame wasn't usable: {frame.reason})"
        if attempt < attempts - 1:
            client.wait(POLL)
    raise MenuError(step, f"expected {expected} within {timeout:g} s{reason}")


def _usable(sprites: ReaderSprites) -> Callable[[Frame], Frame | NotYet]:
    check = FrameCheck(sprites)

    def usable(frame: Frame) -> Frame | NotYet:
        unusable = check.frame_usable(frame)
        return frame if unusable is None else NotYet(unusable.detail)

    return usable


# --- the steps -----------------------------------------------------------------


def open_game_menu(client: Client, sprites: ReaderSprites) -> GameMenu:
    """Presses Escape, unless the Game Menu is already open, and finds it."""
    frame = wait_for(client, "open the Game Menu", _usable(sprites), "a usable frame")
    menu = find_game_menu(sprites, frame)
    if menu is not None:
        return menu
    client.press("escape")
    return wait_for(
        client,
        "open the Game Menu",
        lambda f: find_game_menu(sprites, f),
        "the Game Menu after Escape",
    )


def open_options(client: Client, sprites: ReaderSprites) -> OptionsWindow:
    """
    The Options window: found if it is already open, else opened from the Game
    Menu's Game Option button.

    :raises MenuError: The Key Bindings window is open (it swallows Escape), or a
        step didn't show what it should.
    """
    frame = wait_for(client, "open Options", _usable(sprites), "a usable frame")
    if key_bindings_open(sprites, frame):
        raise MenuError(
            "open Options",
            "the Key Bindings window is open, and it swallows Escape: close it "
            "(Cancel), then try again",
        )
    window = find_options(sprites, frame)
    if window is not None:
        return window
    menu = open_game_menu(client, sprites)
    client.click(*menu.game_option)
    return wait_for(
        client,
        "open Options",
        lambda f: find_options(sprites, f),
        "the Options window after clicking Game Option",
    )


def show_graphics(
    client: Client, sprites: ReaderSprites, window: OptionsWindow
) -> OptionsWindow:
    """Selects the Graphics tab, unless it is already selected."""
    if window.selected == GRAPHICS_TAB:
        return window
    client.click(*_centre(sprites, TABS_DISABLED[GRAPHICS_TAB], window.point))

    def graphics(frame: Frame) -> OptionsWindow | None:
        found = find_options(sprites, frame)
        return found if found is not None and found.selected == GRAPHICS_TAB else None

    return wait_for(
        client, "select the Graphics tab", graphics, "the Graphics tab selected"
    )


def set_resolution(
    client: Client, sprites: ReaderSprites, size: tuple[int, int]
) -> tuple[int, int]:
    """
    Sets the client to the windowed `size`, through Options, and returns the
    client size before. Closes the menus, also on failure.

    :raises ValueError: `size` isn't a windowed size the list has.
    :raises MenuError: A step didn't show what it should; the menus were closed
        (or the message says why they couldn't be).
    """
    if size not in WINDOWED_SIZES:
        raise ValueError(f"{size[0]}x{size[1]} isn't a windowed size the client lists")
    row = WINDOWED_SIZES.index(size)
    check = FrameCheck(sprites)
    before = client.size()
    scale = wait_for(
        client,
        "start",
        lambda f: find_scale(check, f),
        "a frame the menus can be read on",
    )
    ui = ScaledClient(client, scale)
    try:
        window = show_graphics(ui, sprites, open_options(ui, sprites))
        combo = resolution_combo(sprites, window)
        if find_list(_latest(ui), combo) is None:
            ui.click(*combo.centre)
        dropdown = wait_for(
            ui,
            "open the resolution list",
            lambda f: find_list(f, combo),
            f"the {LIST_ROWS}-row resolution list under the dropdown",
        )
        _check_list(dropdown, before)
        ui.click(combo.centre[0], dropdown.row_centre_y(row))
        wait_for(
            ui,
            "choose the size",
            lambda f: True if find_list(f, combo) is None else None,
            "the list closed after clicking the row",
        )
        ui.click(*_confirm_centre(sprites, window))
        _wait_for_size(client, size)
        client.fit()
    except Exception as error:
        _close_after(client, sprites, error)
        raise
    close_menus(client, sprites)
    return before


def _wait_for_size(client: Client, size: tuple[int, int]) -> None:
    """
    Waits for the window's client area to be `size`. Read from the window, not a
    frame, since the resize may have put part of it off the screen.
    """
    attempts = max(1, round(RESIZE_TIMEOUT / POLL))
    now = client.size()
    for attempt in range(attempts):
        now = client.size()
        if now == size:
            return
        if attempt < attempts - 1:
            client.wait(POLL)
    raise MenuError(
        "confirm",
        f"expected the client at {size[0]}x{size[1]} after Confirm within "
        f"{RESIZE_TIMEOUT:g} s; it is {now[0]}x{now[1]}",
    )


def _latest(client: Client) -> Frame:
    return wait_for(client, "read the screen", lambda f: f, "a usable frame")


def _check_list(dropdown: DropdownList, before: tuple[int, int]) -> None:
    """The highlighted row is the client's size, when the client is at one."""
    if before not in WINDOWED_SIZES or dropdown.focused is None:
        return
    expected = WINDOWED_SIZES.index(before)
    if dropdown.focused != expected:
        raise MenuError(
            "open the resolution list",
            f"row {dropdown.focused} is highlighted, but the client is "
            f"{before[0]}x{before[1]}, row {expected}: the list isn't the one "
            "expected",
        )


def _close_after(client: Client, sprites: ReaderSprites, error: Exception) -> None:
    """
    Puts the client area on the primary monitor and closes the menus after
    `error`, saying so on it when that fails too.
    """
    try:
        client.fit()
        close_menus(client, sprites)
    except Exception as closing:  # noqa: BLE001 - reported on `error`, which is raised
        if isinstance(error, MenuError):
            error.detail += f". Then closing the menus failed: {closing}"
            error.args = (f"{error.step}: {error.detail}",)
        else:
            error.add_note(f"Then closing the menus failed: {closing}")


def open_menus(
    sprites: ReaderSprites, frame: Frame, scales: tuple[int, ...] = (1,)
) -> list[str]:
    """
    What is open that Escape closes: the Options window, the Game Menu. Looked
    for at each of `scales` in turn, until one shows something.
    """
    for scale in scales:
        scaled = at_scale(frame, scale)
        found: list[str] = []
        if find_options(sprites, scaled) is not None:
            found.append("the Options window")
        if find_game_menu(sprites, scaled) is not None:
            found.append("the Game Menu")
        if found:
            return found
    return []


def _scales(check: FrameCheck, frame: Frame) -> tuple[int, ...]:
    """The scale the status bar is drawn at; every one when it can't be found."""
    scale = find_scale(check, frame)
    return UI_SCALES if isinstance(scale, NotYet) else (scale,)


def close_menus(client: Client, sprites: ReaderSprites) -> None:
    """
    Presses Escape until neither the Options window nor the Game Menu shows, at
    most `MAX_ESCAPES` times. Sends nothing when none is open. They are looked for
    at the status bar's scale, or at every one of `UI_SCALES` when the status
    bar can't be found.

    :raises MenuError: The Key Bindings window is open, or something is still
        open after `MAX_ESCAPES` presses.
    """
    check = FrameCheck(sprites)
    escapes = 0
    while True:
        frame = wait_for(client, "close the menus", lambda f: f, "a usable frame")
        scales = _scales(check, frame)
        if any(key_bindings_open(sprites, at_scale(frame, s)) for s in scales):
            raise MenuError(
                "close the menus",
                "the Key Bindings window is open, and it swallows Escape: close it "
                "(Cancel) by hand",
            )
        showing = open_menus(sprites, frame, scales)
        if not showing:
            return
        if escapes == MAX_ESCAPES:
            raise MenuError(
                "close the menus",
                f"{' and '.join(showing)} still open after {MAX_ESCAPES} Escapes",
            )
        client.press("escape")
        escapes += 1
        try:
            wait_for(
                client,
                "close the menus",
                lambda f, was=showing: (
                    True if open_menus(sprites, f, _scales(check, f)) != was else None
                ),
                "a menu to close",
            )
        except MenuError:
            pass  # checked again at the top
