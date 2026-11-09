"""
Label a folder of frames with the camera, our character's feet and the
minimap's reading, in virtual px, by running the POC trackers once, offline.
A labelling step for the frame sets (`tests/frames/README.md`), not a reader:
no test imports it.

    python toolkit/poc_tracking/label_frames.py --map 10001000 \
        --frames DIR --glob "henesys_1366x768_*.png" \
        --tag DIR/henesys_1366x768_00.png:624,583,686,596 --out henesys_1366.csv

**Offline only:** it reads PNGs from a folder and never sends a key or a
click.

Each frame, in name order (the trackers are seeded by the previous frame):

- **Minimap** (`hybrid_tracker.MinimapTracker`): the marker's canvas pixel,
  and the feet it implies.
- **Camera, two reads.** `world_tracker`'s registration: exact-colour voting
  at 1:1, and on larger clients a coarse NCC proposal checked by the share of
  pixels near the render upscaled bilinearly. And `hybrid_tracker`'s: exact
  voting at 1:1, a masked NCC seeded by its last camera or the minimap on
  larger clients. Both in virtual px. The play area's size comes from
  `PLAY_AREA`, measured on these frames.
- **Feet.** Our character's own name tag, matched as a template cut from one
  frame with the same play-area scale (`--tag FRAME:x0,y0,x1,y1[:TO_FEET]`,
  the box of its text), anywhere above the status bar: no other character
  carries that text. The feet are the box's centre column, and TO_FEET
  play-area px above the box's top. `hybrid_tracker`'s own tag read and its
  fused status (the minimap and the play area agree or not) are written
  beside it.

The CSV has one row per frame, for a person to check on overlays before the
rows become expected readings.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from game_data.catalogue import Catalogue
from game_data.config import STORE
from toolkit.poc_tracking import hybrid_tracker, world_tracker

PLAY_AREA: dict[tuple[int, int], tuple[int, int]] = {
    (1920, 1080): (1366, 768),
    (1920, 1200): (1228, 768),
    (2560, 1440): (1366, 768),
}
"""The play area's size, in virtual px, on clients that upscale it; smaller
clients draw it 1:1. Measured on frame sets v2 and v3 by the near share
(`world_tracker.StaticMap.bilinear_share`): at 1920x1200 it peaks at 1228
wide (0.89 to 0.91) and not at 1229 or 1230; at 1920x1080 and 2560x1440 at
1366 and not 1365. At 2560x1440 the whole client is upscaled, the UI too."""
TAG_SCORE_OK = 0.8
"""The normalised correlation our tag's template needs where it is found."""

FIELDS = [
    "frame",
    "width",
    "height",
    "view_w",
    "view_h",
    "mm_status",
    "mm_canvas_x",
    "mm_canvas_y",
    "mm_feet_x",
    "mm_feet_y",
    "cam_w_x",
    "cam_w_y",
    "cam_w_detail",
    "cam_h_x",
    "cam_h_y",
    "cam_h_method",
    "tag_score",
    "tag_x",
    "tag_y",
    "feet_x",
    "feet_y",
    "feet_h_x",
    "feet_h_y",
    "fused",
]


def play_area(width: int, height: int) -> tuple[int, int]:
    """The play area's size, in virtual px, on a client of this size."""
    if (width, height) in PLAY_AREA:
        return PLAY_AREA[width, height]
    if width > 1366 or height > 768:
        raise SystemExit(f"no play area measured for {width}x{height}")
    return width, height


@dataclass(frozen=True)
class TagTemplate:
    """
    Our name tag's text, cut from a frame (lightest channel, as float), for
    frames whose play area is upscaled as that frame's is.

    :ivar scale: The play area's upscale, x and y, in the frame it was cut from.
    :ivar to_feet: Play-area px from the feet down to the template's top.
    """

    pixels: NDArray[np.float32]
    scale: tuple[float, float]
    to_feet: float

    @classmethod
    def cut(cls, spec: str) -> TagTemplate:
        """From `FRAME:x0,y0,x1,y1[:TO_FEET]`, FRAME a path to a PNG."""
        name, box = spec.rsplit(":", 1)
        to_feet = float(hybrid_tracker.TAG_TO_FEET)
        if "," not in box:
            name, box, to_feet = *name.rsplit(":", 1), float(box)
        x0, y0, x1, y1 = (int(v) for v in box.split(","))
        image = cv2.imread(name, cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"can't read the tag's frame {name}")
        h, w = image.shape[:2]
        return cls(_lightest(image[y0:y1, x0:x1]), _scale(w, h), to_feet)

    def find(
        self, frame: NDArray[np.uint8], bottom: int
    ) -> tuple[float, int, int] | None:
        """The best match's score and top-left, over the frame less its
        `bottom` rows (the status bar, which shows the character's name)."""
        hay = _lightest(frame[: frame.shape[0] - bottom])
        th, tw = self.pixels.shape
        if hay.shape[0] < th or hay.shape[1] < tw:
            return None
        score = cv2.matchTemplate(hay, self.pixels, cv2.TM_CCOEFF_NORMED)
        score = np.nan_to_num(score, nan=-1.0)
        _, best, _, (x, y) = cv2.minMaxLoc(score)
        return float(best), int(x), int(y)


def _scale(width: int, height: int) -> tuple[float, float]:
    view = play_area(width, height)
    return width / view[0], height / view[1]


def _lightest(image: NDArray[np.uint8]) -> NDArray[np.float32]:
    return image.min(axis=2).astype(np.float32)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.1f}"


def label(
    map_text: str,
    frames: Path,
    pattern: str,
    tags: list[TagTemplate],
    bottom: int,
    out: Path,
) -> None:
    assets = hybrid_tracker.load_assets(STORE, map_text, REPO / "data" / "poc_tracking")
    minimap = hybrid_tracker.MinimapTracker(assets)
    hybrid = hybrid_tracker.WorldTracker(assets, None)
    with Catalogue.latest(STORE) as cat:
        static = world_tracker.WorldTracker(cat, assets.data, STORE, False).static
    rng = np.random.default_rng(0)
    vx, vy = assets.origin
    last: tuple[int, int] | None = None  # world_tracker's last camera, render px
    rows: list[dict[str, str]] = []
    for path in sorted(frames.glob(pattern)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        h, w = image.shape[:2]
        view = play_area(w, h)
        sx, sy = _scale(w, h)
        mm = minimap.read(image)
        hy = hybrid.read(image, mm.feet if mm.ok else None)
        fused = hybrid_tracker.fuse(mm, hy, assets.data)
        if (sx, sy) == (1.0, 1.0):
            reg = static.register_exact(image, last, rng)
        else:
            reg = static.register_scaled(image, view, last, rng)
            if not reg.ok and last is not None:
                reg = static.register_scaled(image, view, None, rng)
        last = reg.camera if reg.ok else None
        row = dict.fromkeys(FIELDS, "")
        row.update(
            frame=path.name,
            width=str(w),
            height=str(h),
            view_w=str(view[0]),
            view_h=str(view[1]),
            mm_status=mm.status,
            cam_w_detail=reg.detail,
            cam_h_method=hy.camera_method or hy.status,
            fused=fused.status,
        )
        if mm.ok and mm.canvas_pos is not None and mm.feet is not None:
            row.update(
                mm_canvas_x=str(mm.canvas_pos[0]),
                mm_canvas_y=str(mm.canvas_pos[1]),
                mm_feet_x=_fmt(mm.feet[0]),
                mm_feet_y=_fmt(mm.feet[1]),
            )
        camera = None
        if reg.ok and reg.camera is not None:
            camera = (reg.camera[0] + vx, reg.camera[1] + vy)
            row.update(cam_w_x=str(camera[0]), cam_w_y=str(camera[1]))
        if hy.camera is not None:
            row.update(cam_h_x=str(hy.camera[0]), cam_h_y=str(hy.camera[1]))
        if hy.world is not None:
            row.update(feet_h_x=_fmt(hy.world[0]), feet_h_y=_fmt(hy.world[1]))
        tag = next(
            (t for t in tags if math.isclose(t.scale[1], sy, abs_tol=1e-3)), None
        )
        found = None if tag is None else tag.find(image, bottom)
        if tag is not None and found is not None:
            score, x, y = found
            row.update(tag_score=f"{score:.3f}", tag_x=str(x), tag_y=str(y))
            if score >= TAG_SCORE_OK and camera is not None:
                tw = tag.pixels.shape[1]
                fx = camera[0] + (x + (tw - 1) / 2) / sx
                fy = camera[1] + y / sy - tag.to_feet
                row.update(feet_x=_fmt(fx), feet_y=_fmt(fy))
        rows.append(row)
        print(
            f"{path.name:36s} mm {row['mm_canvas_x']:>4s},{row['mm_canvas_y']:>4s} "
            f"cam {row['cam_w_x']:>6s},{row['cam_w_y']:>6s} "
            f"hybrid {row['cam_h_x']:>6s},{row['cam_h_y']:>6s} "
            f"tag {row['tag_score']:>6s} feet {row['feet_x']:>7s},{row['feet_y']:>7s} "
            f"{fused.status}",
            flush=True,
        )
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--map", required=True, help="map ID or unique name")
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--glob", default="*.png")
    parser.add_argument(
        "--tag",
        action="append",
        required=True,
        help=(
            "FRAME:x0,y0,x1,y1[:TO_FEET]: our name tag's text in FRAME (a path), "
            "matched on frames whose play area is upscaled as FRAME's is; TO_FEET, "
            "the play-area px from the feet down to the box's top (default "
            f"{hybrid_tracker.TAG_TO_FEET}). Repeat it for each upscale."
        ),
    )
    parser.add_argument(
        "--bottom",
        type=int,
        default=80,
        help="client px at the bottom not searched for the tag (the status bar)",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    tags = [TagTemplate.cut(spec) for spec in args.tag]
    label(args.map, args.frames, args.glob, tags, args.bottom, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
