"""
The probe: ``python -m maple.probe``, a CLI for looking at the game window when no
Session is running (intent #331).

This module only looks. ``screenshot``, ``regions`` and ``keys`` send no input, so
nothing here touches the Held-Keys Ledger or releases a key.

One coordinate frame: pixel (x, y) of a full-window PNG is the probe's coordinate.
That PNG excludes the title bar and border, whereas the interface boxes and
``take_screenshot`` work in window-rect coordinates, so ``--box`` is shifted by the
client margins before it reaches them.

Exit codes: 0 ok, 1 other error, 2 usage, 3 region not showing, 4 no client open,
5 several clients open.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import win32gui

from botting.controller.high_level import key_binds
from botting.utilities import (
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
    Box,
    take_screenshot,
)
from botting.utilities.client_handler import get_client_handle, get_open_clients
from maple import maple_ign_finder
from maple.model.interface import CharacterStats, InventoryMenu, LargeClientChatFeed
from maple.model.interface import Minimap as _Minimap
from paths import ROOT

EXIT_ERROR = 1
EXIT_NOT_SHOWING = 3
EXIT_NO_CLIENT = 4
EXIT_SEVERAL_CLIENTS = 5

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


# --- entry point -------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--ign", help="pick the client by IGN (default: the only one open)"
    )

    parser = argparse.ArgumentParser(
        prog="python -m maple.probe", description="Look at the game window."
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = args.run(args)
    except ProbeError as err:
        sys.stderr.write(err.message + "\n")
        return err.code
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
