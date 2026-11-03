"""Save frames of the running client for the frame set.

    python toolkit/capture_frames.py OUT_DIR [--count 10] [--interval 2.0]

Keeps only frames the frame check passes (`FrameCheck.frame_usable`: the copy is
trustworthy and the UI is at 1:1, "UI Size: Ideal Ratio") and writes each as a PNG in
OUT_DIR, plus a stub entry for it in OUT_DIR/frames.json for a person to
complete (`notes` and `expect`) before it is committed as `tests/frames/<tag>.json`.

The PNGs can show other players' names: they go only to the private
`legends-frames` repository, never into git.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import cv2

from botting.screen import Frame, FrameSource, Reading, frame_source

MANIFEST = "frames.json"


def stub_entry(file: str, frame: Frame) -> dict[str, Any]:
    width, height = frame.client_size
    return {"file": file, "client_size": [width, height], "notes": "", "expect": {}}


class Check(Protocol):
    """The part of `maple.screen.locator.FrameCheck` used here."""

    def frame_usable(self, frame: Frame) -> Reading[None] | None: ...


def save_frame(frame: Frame, out_dir: Path, check: Check) -> str | None:
    """
    Write `frame` and its stub entry; return the file name, or None when
    `check.frame_usable(frame)` rejects it.
    """
    if check.frame_usable(frame) is not None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    file = f"{frame.client_size[0]}x{frame.client_size[1]}-{stamp}.png"
    if not cv2.imwrite(str(out_dir / file), frame.pixels):
        raise OSError(f"can't write {out_dir / file}")

    manifest = out_dir / MANIFEST
    entries = (
        json.loads(manifest.read_text(encoding="utf-8"))["frames"]
        if manifest.exists()
        else []
    )
    entries.append(stub_entry(file, frame))
    manifest.write_text(
        json.dumps({"frames": entries}, indent=2) + "\n", encoding="utf-8"
    )
    return file


def capture(
    source: FrameSource,
    handle: int,
    out_dir: Path,
    count: int,
    interval: float,
    check: Check,
) -> int:
    """Grab `count` frames `interval` seconds apart; return how many were kept."""
    kept = 0
    for i in range(count):
        if i:
            time.sleep(interval)
        frame = source.grab(handle)
        file = save_frame(frame, out_dir, check)
        if file is None:
            rejected = check.frame_usable(frame)
            print(f"skipped: {rejected.detail if rejected else 'not usable'}")
        else:
            kept += 1
            print(f"saved {file}")
    return kept


if __name__ == "__main__":
    from maple.screen.client import find_client
    from maple.screen.locator import FrameCheck
    from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    sprites = load_reader_sprites([FRAME_CHECK], Profile(job="", game_map=""))
    kept = capture(
        frame_source(),
        find_client(),
        args.out_dir,
        args.count,
        args.interval,
        FrameCheck(sprites),
    )
    print(f"{kept}/{args.count} frames kept in {args.out_dir}")
