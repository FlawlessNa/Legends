"""
The probe: ``python -m maple.probe``, a CLI for looking at the game window, and
sending it simple input, when no Session is running (intent #331).

``screenshot``, ``regions`` and ``keys`` send no input, so they touch neither the
Held-Keys Ledger nor any key.

``press``, ``hold``, ``write`` and ``click`` are each one complete gesture, run by
`run_guarded` (ADR 0002): validate everything first, so a refusal sends nothing; bring
the client to the front; reset the ledger and `release_all` while the client is in
front (the start-up reconciliation); run the gesture through the bot's own input
functions; and `release_all` in a ``finally``. No command sends a lone keydown or
keyup.

One coordinate frame: pixel (x, y) of a full-window PNG is the probe's coordinate.
That PNG excludes the title bar and border, whereas the interface boxes and
``take_screenshot`` work in window-rect coordinates, so ``--box`` is shifted by the
client margins before it reaches them.

Exit codes: 0 ok, 1 other error, 2 usage or refused input (nothing sent), 3 region
not showing, 4 no client open, 5 several clients open, 130 interrupted (keys
released).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import win32gui

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
from botting.utilities import (
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
    Box,
    take_screenshot,
)
from botting.utilities.client_handler import get_client_handle, get_open_clients
from maple import maple_ign_finder
from maple.actions.movements_v2 import move
from maple.model.interface import CharacterStats, InventoryMenu, LargeClientChatFeed
from maple.model.interface import Minimap as _Minimap
from paths import ROOT

EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_NOT_SHOWING = 3
EXIT_NO_CLIENT = 4
EXIT_SEVERAL_CLIENTS = 5
EXIT_INTERRUPTED = 130

MAX_TIMES = 10
MAX_MS = 10_000
DIRECTIONS = ("left", "right", "up", "down")

PROBE_DIR = Path(ROOT) / "probe"
KEEP_LAST = 50

# Static regions: window-rect boxes that never move.
STATIC_REGIONS: dict[str, Box] = {
    "ign": CharacterStats.ign_box,
    "level": CharacterStats.level_box,
    "job": CharacterStats.job_box,
    "hp_bar": CharacterStats.hp_bar_box,
    "mp_bar": CharacterStats.mp_bar_box,
    "exp_bar": CharacterStats.exp_bar_box,
}


class ProbeError(Exception):
    """A failure with the exit code the probe should return."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- dynamic regions ---------------------------------------------------------
# Each finder returns the region's window-rect box, or None when it isn't showing.
# `image` is a full-window screenshot to reuse, or None to take one.
#
# There is no `ability_menu` region: AbilityMenu only holds offsets for individual
# stat fields from its icon, and no box for the whole menu.


class _ProbeMinimap(_Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        return image


def _find_minimap(handle: int, image: np.ndarray | None) -> Box | None:
    return _ProbeMinimap().get_entire_minimap_box(handle, image)


def _find_inventory(handle: int, image: np.ndarray | None) -> Box | None:
    menu = InventoryMenu()
    return menu.get_abs_box(handle, menu._entire_inventory_box, image)


def _find_chat(handle: int, image: np.ndarray | None) -> Box | None:
    del image
    return LargeClientChatFeed().get_chat_feed_box(handle)


DYNAMIC_REGIONS: dict[str, Callable[[int, np.ndarray | None], Box | None]] = {
    "minimap": _find_minimap,
    "inventory": _find_inventory,
    "chat": _find_chat,
}

REGION_NAMES = (*STATIC_REGIONS, *DYNAMIC_REGIONS)


def _lookup(name: str, handle: int, image: np.ndarray | None = None) -> Box | None:
    try:
        return DYNAMIC_REGIONS[name](handle, image)
    except ValueError as err:  # e.g. "More than one menu icon detected"
        raise ProbeError(EXIT_NOT_SHOWING, f"Region {name!r} is ambiguous: {err}")


# --- coordinates -------------------------------------------------------------


def window_box(left: int, top: int, right: int, bottom: int) -> Box:
    """A box in PNG coordinates, as a window-rect box (adds the title bar and border)."""
    return Box(
        left=left + CLIENT_HORIZONTAL_MARGIN_PX,
        top=top + CLIENT_VERTICAL_MARGIN_PX,
        right=right + CLIENT_HORIZONTAL_MARGIN_PX,
        bottom=bottom + CLIENT_VERTICAL_MARGIN_PX,
    )


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


# --- window ------------------------------------------------------------------


def _describe_clients(handles: Sequence[int]) -> str:
    return ", ".join(f"{h} ({maple_ign_finder(h)})" for h in handles)


def resolve_handle(ign: str | None) -> int:
    if ign is not None:
        try:
            return get_client_handle(ign, maple_ign_finder)
        except ValueError as err:
            raise ProbeError(EXIT_NO_CLIENT, str(err))
    handles = get_open_clients()
    if not handles:
        raise ProbeError(EXIT_NO_CLIENT, "No game client is open.")
    if len(handles) > 1:
        raise ProbeError(
            EXIT_SEVERAL_CLIENTS,
            "Several clients are open, pass --ign. Open: " + _describe_clients(handles),
        )
    return handles[0]


def resolve_ign(ign: str | None, handle: int) -> str:
    return ign if ign is not None else maple_ign_finder(handle)


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
    handle = resolve_handle(args.ign)
    if args.region is not None:
        label = args.region
        if args.region in STATIC_REGIONS:
            box = STATIC_REGIONS[args.region]
        else:
            box = _lookup(args.region, handle)
            if box is None:
                raise ProbeError(
                    EXIT_NOT_SHOWING, f"Region {args.region!r} is not showing."
                )
        image = take_screenshot(handle, box)
    elif args.box is not None:
        label = "box"
        width, height = _client_size(handle)
        if args.box[2] > width or args.box[3] > height:
            raise ProbeError(
                EXIT_ERROR, f"Box {args.box} is outside the {width}x{height} window."
            )
        image = take_screenshot(handle, window_box(*args.box))
    else:
        label = "window"
        image = take_screenshot(handle)
    path = save_png(image, label)
    height, width = image.shape[:2]
    return {"ok": True, "path": _display_path(path), "w": width, "h": height}


def cmd_regions(args: argparse.Namespace) -> dict:
    handle = resolve_handle(args.ign)
    image = take_screenshot(handle)
    dynamic = {
        name: _lookup(name, handle, image) is not None for name in DYNAMIC_REGIONS
    }
    return {"ok": True, "static": list(STATIC_REGIONS), "dynamic": dynamic}


def cmd_keys(args: argparse.Namespace) -> dict:
    handle = resolve_handle(args.ign)
    ign = resolve_ign(args.ign, handle)
    try:
        names = sorted(key_binds(ign))
    except (AssertionError, KeyError) as err:
        raise ProbeError(EXIT_ERROR, f"No key bindings for {ign!r}: {err}")
    return {"ok": True, "ign": ign, "keys": names}


# --- input -------------------------------------------------------------------


def _bindings(ign: str) -> dict[str, str]:
    """The IGN's bindings, by lower-cased name, or none when it has no section."""
    try:
        return {name.lower(): key for name, key in key_binds(ign).items()}
    except AssertionError, KeyError:
        return {}


def resolve_key(name: str, handle: int, ign: str) -> str:
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
    handle = resolve_handle(args.ign)
    key = resolve_key(args.key, handle, resolve_ign(args.ign, handle))

    async def gesture() -> None:
        for _ in range(args.times):
            await press(handle, key)

    return _send(handle, gesture, {"ok": True, "pressed": key, "times": args.times})


def cmd_hold(args: argparse.Namespace) -> dict:
    handle = resolve_handle(args.ign)

    async def gesture() -> None:
        await move(handle, args.direction, duration=args.ms / 1000).send()
        release_directions(handle)

    return _send(handle, gesture, {"ok": True, "held": args.direction, "ms": args.ms})


def cmd_write(args: argparse.Namespace) -> dict:
    handle = resolve_handle(args.ign)

    async def gesture() -> None:
        await write(handle, args.text)

    return _send(handle, gesture, {"ok": True, "wrote": args.text})


def cmd_click(args: argparse.Namespace) -> dict:
    handle = resolve_handle(args.ign)
    width, height = _client_size(handle)
    if args.x >= width or args.y >= height:
        raise ProbeError(
            EXIT_REFUSED,
            f"({args.x}, {args.y}) is outside the {width}x{height} window.",
        )
    # `mouse_move` wants window-rect coordinates: add the title bar and border.
    target = (args.x + CLIENT_HORIZONTAL_MARGIN_PX, args.y + CLIENT_VERTICAL_MARGIN_PX)

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
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--ign", help="pick the client by IGN (default: the only one open)"
    )

    parser = argparse.ArgumentParser(
        prog="python -m maple.probe",
        description="Look at the game window, and send it simple input.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    shot = sub.add_parser("screenshot", parents=[common], help="save a PNG to probe/")
    which = shot.add_mutually_exclusive_group()
    which.add_argument("--region", choices=REGION_NAMES)
    which.add_argument(
        "--box",
        type=_parse_box,
        metavar="l,t,r,b",
        help="a box in full-window PNG pixels",
    )
    shot.set_defaults(run=cmd_screenshot)

    sub.add_parser(
        "regions", parents=[common], help="list the regions and which are showing"
    ).set_defaults(run=cmd_regions)
    sub.add_parser(
        "keys", parents=[common], help="list the key binding names"
    ).set_defaults(run=cmd_keys)

    press_ = sub.add_parser(
        "press", parents=[common], help="press a key: keydown, then keyup"
    )
    press_.add_argument("key", help="a binding name (see `keys`) or a key name")
    press_.add_argument(
        "--times", type=_bounded(1, MAX_TIMES), default=1, help=f"1 to {MAX_TIMES}"
    )
    press_.set_defaults(run=cmd_press)

    hold = sub.add_parser(
        "hold", parents=[common], help="hold a direction, then release it"
    )
    hold.add_argument("direction", choices=DIRECTIONS)
    hold.add_argument(
        "--ms", type=_bounded(1, MAX_MS), required=True, help=f"1 to {MAX_MS}"
    )
    hold.set_defaults(run=cmd_hold)

    write_ = sub.add_parser(
        "write", parents=[common], help="type text into the chat box, already open"
    )
    write_.add_argument("text")
    write_.set_defaults(run=cmd_write)

    click_ = sub.add_parser(
        "click", parents=[common], help="left-click at full-window PNG pixels"
    )
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
