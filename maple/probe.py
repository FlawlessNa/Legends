"""
The probe: ``python -m maple.probe``, a CLI for looking at the game window, and
sending it simple input, when no Session is running (intent #331).

**The window** is the one MapleStory client, found by `maple.screen.client.find_client`
(its class and executable, from `configs/game.ini`): neither its title nor its
screen is read. ``--ign`` only names the `configs/keybindings.ini` section that
binding names come from; without it, the file's only section is used.

``screenshot``, ``regions`` and ``keys`` send no input, so they touch neither the
Held-Keys Ledger nor any key. ``screenshot`` and ``regions`` capture through
`FrameSource` (Desktop Duplication), which copies what is on screen: a frame that
isn't the client's own pixels (the client not in front, covered, moved) is refused
with its reason, and no PNG is written.

``press``, ``hold``, ``write`` and ``click`` are each one complete gesture, run by
`run_guarded` (ADR 0002): validate everything first, so a refusal sends nothing; bring
the client to the front; reset the ledger and `release_all` while the client is in
front (the start-up reconciliation); run the gesture through the bot's own input
functions; and `release_all` in a ``finally``. No command sends a lone keydown or
keyup.

One coordinate frame: pixel (x, y) of a full-window PNG is the probe's coordinate.
That PNG is a `Frame`: the client area, in physical pixels. ``--box``, the regions
and `mouse_move` (through ``ClientToScreen``) all use the same pixels, so no margin
is added anywhere.

Exit codes: 0 ok, 1 other error, 2 usage or refused input (nothing sent), 3 region
not showing, 4 no client open, 5 several clients open, 6 the frame isn't the
client's own pixels (nothing written), 130 interrupted (keys released).
"""

import argparse
import asyncio
import functools
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import win32gui
from numpy.typing import NDArray

from botting.controller.high_level import (
    key_binds,
    mouse_move_and_click,
    press,
    write,
)
from botting.controller.inputs import (
    HeldKeysLedger,
    SharedResources,
    input_constructor,
    release_all,
    release_directions,
)
from botting.controller.inputs.focused_inputs import activate
from botting.screen import Frame, MultipleWindows, WindowNotFound, frame_source
from botting.utilities import Box, config_reader
from maple.actions.movements_v2 import move
from maple.screen.buffs import BUFFS, ICON_BASE, BuffsReader
from maple.screen.client import find_client
from maple.screen.locator import FrameCheck, unreadable
from maple.screen.minimap import MINIMAP, MinimapReader
from maple.screen.sprites import (
    FRAME_CHECK,
    Profile,
    StartupRefused,
    load_reader_sprites,
)
from maple.screen.status_bar import STATUS_BAR, StatusBarReader
from paths import ROOT

EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_NOT_SHOWING = 3
EXIT_NO_CLIENT = 4
EXIT_SEVERAL_CLIENTS = 5
EXIT_FRAME_NOT_OK = 6
EXIT_INTERRUPTED = 130

MAX_TIMES = 10
MAX_MS = 10_000
DIRECTIONS = ("left", "right", "up", "down")

PROBE_DIR = Path(ROOT) / "probe"
KEEP_LAST = 50


class ProbeError(Exception):
    """A failure with the exit code the probe should return."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- regions -----------------------------------------------------------------
# Every region is found in the frame by a `maple.screen` reader, in client pixels.
# A finder returns the region's box, or why it isn't showing.


@dataclass(frozen=True)
class Readers:
    """The readers the regions come from, sharing one frame check."""

    frame_check: FrameCheck
    status_bar: StatusBarReader
    minimap: MinimapReader
    buffs: BuffsReader
    buff_size: tuple[int, int]


@functools.cache
def readers() -> Readers:
    """
    The readers, their sprites loaded from the `game_data` store on first use, so a
    plain screenshot doesn't need the store.
    """
    try:
        sprites = load_reader_sprites(
            [FRAME_CHECK, STATUS_BAR, MINIMAP, BUFFS], Profile(job="", game_map="")
        )
    except StartupRefused as err:
        raise ProbeError(EXIT_ERROR, f"The regions need the game data: {err}")
    check = FrameCheck(sprites)
    base = sprites.canvas(ICON_BASE).rgba
    return Readers(
        frame_check=check,
        status_bar=StatusBarReader(sprites, check),
        minimap=MinimapReader(sprites, check),
        buffs=BuffsReader(sprites, check),
        buff_size=(base.shape[1], base.shape[0]),
    )


type Finder = Callable[[Readers, Frame], Box | str]


def _status_bar(part: str) -> Finder:
    def find(found: Readers, frame: Frame) -> Box | str:
        unusable = found.frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable.detail
        located = found.status_bar.locator.locate(frame)
        missing = unreadable(located, frame)
        if missing is not None:
            return f"status bar {missing.status.value}: {missing.detail}"
        assert located is not None
        return found.status_bar.boxes(located)[part]

    return find


def _minimap(found: Readers, frame: Frame) -> Box | str:
    reading = found.minimap.read(frame)
    if reading.value is None:
        return f"minimap {reading.status.value}: {reading.detail}"
    return reading.value.bounds


def _buffs(found: Readers, frame: Frame) -> Box | str:
    unusable = found.frame_check.frame_usable(frame)
    if unusable is not None:
        return unusable.detail
    slots = found.buffs.slots(frame.pixels)
    if not slots:
        return "no buff slot found"
    width, height = found.buff_size
    return Box(
        left=min(x for x, _ in slots),
        top=min(y for _, y in slots),
        right=max(x for x, _ in slots) + width,
        bottom=max(y for _, y in slots) + height,
    )


# No reader in `maple.screen` gives the IGN, the job, the inventory (parked, see
# `maple/AGENTS.md`), the chat or the quick slots, so they have no region.
REGIONS: dict[str, Finder] = {
    "status_bar": _status_bar("bar"),
    "level": _status_bar("level"),
    "hp": _status_bar("hp"),
    "mp": _status_bar("mp"),
    "exp": _status_bar("exp"),
    "minimap": _minimap,
    "buffs": _buffs,
}


def find_region(name: str, frame: Frame) -> Box:
    found = REGIONS[name](readers(), frame)
    if isinstance(found, str):
        raise ProbeError(EXIT_NOT_SHOWING, f"Region {name!r} is not showing: {found}")
    return found


# --- coordinates and capture -------------------------------------------------


def _parse_box(text: str) -> tuple[int, int, int, int]:
    try:
        left, top, right, bottom = (int(part) for part in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected l,t,r,b integers, got {text!r}")
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise argparse.ArgumentTypeError(
            f"need 0 <= l < r and 0 <= t < b, got {text!r}"
        )
    return left, top, right, bottom


def _client_size(handle: int) -> tuple[int, int]:
    _left, _top, right, bottom = win32gui.GetClientRect(handle)
    return right, bottom


def grab(handle: int) -> Frame:
    """The client's frame; a `ProbeError` with the frame's reason when it isn't ok."""
    frame = frame_source().grab(handle)
    if not frame.ok:
        raise ProbeError(
            EXIT_FRAME_NOT_OK,
            f"The frame isn't the client's own pixels: {frame.reason}. Nothing was "
            "written. Bring the client to the front, uncovered, and try again.",
        )
    return frame


def crop(frame: Frame, box: Box) -> NDArray[np.uint8]:
    width, height = frame.client_size
    return frame.pixels[
        max(box.top, 0) : min(box.bottom, height),
        max(box.left, 0) : min(box.right, width),
    ]


# --- window and bindings -----------------------------------------------------


def resolve_handle() -> int:
    try:
        return find_client()
    except WindowNotFound as err:
        raise ProbeError(EXIT_NO_CLIENT, str(err))
    except MultipleWindows as err:
        raise ProbeError(EXIT_SEVERAL_CLIENTS, str(err))


def _binding_sections() -> list[str]:
    try:
        config = config_reader("keybindings")
    except AssertionError:  # configs/keybindings.ini doesn't exist
        return []
    assert isinstance(config, ConfigParser)
    return config.sections()


def resolve_ign(ign: str | None) -> str | None:
    """The keybindings section to use: `ign`, else the file's only section, else None."""
    if ign is not None:
        return ign
    sections = _binding_sections()
    return sections[0] if len(sections) == 1 else None


# --- files -------------------------------------------------------------------


def _timestamp(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=UTC).astimezone()
    return now.strftime("%Y-%m-%d_%H-%M-%S-") + f"{now.microsecond // 1000:03d}"


def prune(directory: Path, keep: int = KEEP_LAST) -> None:
    """Keep the `keep` most recent PNGs. Names start with a timestamp, so they sort."""
    for old in sorted(directory.glob("*.png"))[:-keep]:
        old.unlink(missing_ok=True)


def save_png(image: np.ndarray, label: str) -> Path:
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    path = PROBE_DIR / f"{_timestamp()}_{label}.png"
    if not cv2.imwrite(str(path), image):
        raise ProbeError(EXIT_ERROR, f"Could not write {path}.")
    prune(PROBE_DIR)
    return path


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# --- commands ----------------------------------------------------------------


def cmd_screenshot(args: argparse.Namespace) -> dict:
    frame = grab(resolve_handle())
    if args.region is not None:
        label = args.region
        image = crop(frame, find_region(args.region, frame))
    elif args.box is not None:
        label = "box"
        width, height = frame.client_size
        left, top, right, bottom = args.box
        if right > width or bottom > height:
            raise ProbeError(
                EXIT_ERROR, f"Box {args.box} is outside the {width}x{height} window."
            )
        image = crop(frame, Box(left=left, top=top, right=right, bottom=bottom))
    else:
        label = "window"
        image = frame.pixels
    path = save_png(image, label)
    height, width = image.shape[:2]
    return {"ok": True, "path": _display_path(path), "w": width, "h": height}


def cmd_regions(args: argparse.Namespace) -> dict:
    """Each region's box `[l, t, r, b]` in PNG pixels, or null when it isn't showing."""
    del args
    frame = grab(resolve_handle())
    found = readers()
    showing: dict[str, list[int] | None] = {}
    for name, finder in REGIONS.items():
        box = finder(found, frame)
        showing[name] = (
            None if isinstance(box, str) else [box.left, box.top, box.right, box.bottom]
        )
    return {"ok": True, "regions": showing}


def cmd_keys(args: argparse.Namespace) -> dict:
    ign = resolve_ign(args.ign)
    if ign is None:
        raise ProbeError(
            EXIT_ERROR,
            "Pass --ign: configs/keybindings.ini doesn't have exactly one section "
            f"(it has {_binding_sections()}).",
        )
    try:
        names = sorted(key_binds(ign))
    except (AssertionError, KeyError) as err:
        raise ProbeError(EXIT_ERROR, f"No key bindings for {ign!r}: {err}")
    return {"ok": True, "ign": ign, "keys": names}


# --- input -------------------------------------------------------------------


def _bindings(ign: str | None) -> dict[str, str]:
    """The IGN's bindings, by lower-cased name, or none when it has no section."""
    if ign is None:
        return {}
    try:
        return {name.lower(): key for name, key in key_binds(ign).items()}
    except AssertionError, KeyError:
        return {}


def resolve_key(name: str, handle: int, ign: str | None) -> str:
    """
    A binding name (case-insensitive) or a plain key name, as the key to send.

    A plain key is valid when the input layer can build a keydown for it, which sends
    nothing. Directions are refused, as `press()` refuses them: holding one is `hold`'s
    job.
    """
    key = _bindings(ign).get(name.lower(), name.lower())
    if key in DIRECTIONS:
        raise ProbeError(
            EXIT_REFUSED, f"{name!r} is a direction: use `hold {key} --ms MS`."
        )
    try:
        input_constructor(handle, [[key]], [["keydown"]])
    except (KeyError, AssertionError, TypeError, ValueError) as err:
        raise ProbeError(
            EXIT_REFUSED,
            f"Unknown key {name!r}: neither a binding of {ign!r} nor a key name "
            f"({type(err).__name__}: {err}). `keys` lists the bindings.",
        )
    return key


async def run_guarded(handle: int, gesture: Callable[[], Awaitable[None]]) -> None:
    """
    Runs one gesture inside the probe's guards, in this order: bring the client to
    the front; reset the Held-Keys Ledger and `release_all` (the start-up
    reconciliation, done while the client is in front so the keyups reach it); the
    gesture; and `release_all` in a ``finally``, which also runs on an exception, a
    cancellation or Ctrl+C.
    """
    try:
        if await activate(handle):
            # The gesture's own `focused_inputs` takes the focus lock again.
            SharedResources.focus_lock.release()
        HeldKeysLedger.reset()
        release_all(handle)
        await gesture()
    finally:
        release_all(handle)


def _send(handle: int, gesture: Callable[[], Awaitable[None]], result: dict) -> dict:
    """Runs the gesture in its own event loop, then reports what the ledger holds."""
    asyncio.run(run_guarded(handle, gesture))
    return {**result, "held_after": sorted(HeldKeysLedger.keys_held(handle))}


def cmd_press(args: argparse.Namespace) -> dict:
    handle = resolve_handle()
    key = resolve_key(args.key, handle, resolve_ign(args.ign))

    async def gesture() -> None:
        for _ in range(args.times):
            await press(handle, key)

    return _send(handle, gesture, {"ok": True, "pressed": key, "times": args.times})


def cmd_hold(args: argparse.Namespace) -> dict:
    handle = resolve_handle()

    async def gesture() -> None:
        await move(handle, args.direction, duration=args.ms / 1000).send()
        release_directions(handle)

    return _send(handle, gesture, {"ok": True, "held": args.direction, "ms": args.ms})


def cmd_write(args: argparse.Namespace) -> dict:
    handle = resolve_handle()

    async def gesture() -> None:
        await write(handle, args.text)

    return _send(handle, gesture, {"ok": True, "wrote": args.text})


def cmd_click(args: argparse.Namespace) -> dict:
    handle = resolve_handle()
    width, height = _client_size(handle)
    if args.x >= width or args.y >= height:
        raise ProbeError(
            EXIT_REFUSED,
            f"({args.x}, {args.y}) is outside the {width}x{height} window.",
        )
    # `mouse_move` takes client pixels, the PNG's own, and adds the client's
    # screen origin itself (`ClientToScreen`).
    target = (args.x, args.y)

    async def gesture() -> None:
        await mouse_move_and_click(handle, target)

    return _send(handle, gesture, {"ok": True, "clicked": [args.x, args.y]})


def _bounded(low: int, high: int | None = None) -> Callable[[str], int]:
    """An argparse type: an integer in [low, high]."""

    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected an integer, got {text!r}")
        if value < low or (high is not None and value > high):
            limit = f"{low} to {high}" if high is not None else f"at least {low}"
            raise argparse.ArgumentTypeError(f"must be {limit}, got {value}")
        return value

    return parse


# --- entry point -------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    bindings = argparse.ArgumentParser(add_help=False)
    bindings.add_argument(
        "--ign",
        help="the configs/keybindings.ini section binding names come from "
        "(default: its only section)",
    )

    parser = argparse.ArgumentParser(
        prog="python -m maple.probe",
        description="Look at the game window, and send it simple input.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    shot = sub.add_parser("screenshot", help="save a PNG to probe/")
    which = shot.add_mutually_exclusive_group()
    which.add_argument("--region", choices=tuple(REGIONS))
    which.add_argument(
        "--box",
        type=_parse_box,
        metavar="l,t,r,b",
        help="a box in full-window PNG pixels",
    )
    shot.set_defaults(run=cmd_screenshot)

    sub.add_parser(
        "regions", help="list the regions and where each is showing"
    ).set_defaults(run=cmd_regions)
    sub.add_parser(
        "keys", parents=[bindings], help="list the key binding names"
    ).set_defaults(run=cmd_keys)

    press_ = sub.add_parser(
        "press", parents=[bindings], help="press a key: keydown, then keyup"
    )
    press_.add_argument("key", help="a binding name (see `keys`) or a key name")
    press_.add_argument(
        "--times", type=_bounded(1, MAX_TIMES), default=1, help=f"1 to {MAX_TIMES}"
    )
    press_.set_defaults(run=cmd_press)

    hold = sub.add_parser("hold", help="hold a direction, then release it")
    hold.add_argument("direction", choices=DIRECTIONS)
    hold.add_argument(
        "--ms", type=_bounded(1, MAX_MS), required=True, help=f"1 to {MAX_MS}"
    )
    hold.set_defaults(run=cmd_hold)

    write_ = sub.add_parser("write", help="type text into the chat box, already open")
    write_.add_argument("text")
    write_.set_defaults(run=cmd_write)

    click_ = sub.add_parser("click", help="left-click at full-window PNG pixels")
    click_.add_argument("x", type=_bounded(0))
    click_.add_argument("y", type=_bounded(0))
    click_.set_defaults(run=cmd_click)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = args.run(args)
    except ProbeError as err:
        sys.stderr.write(err.message + "\n")
        return err.code
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted; release_all ran.\n")
        return EXIT_INTERRUPTED
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
