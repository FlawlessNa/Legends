"""Check the player composer on the extract: its coverage, and a contact sheet.

    python toolkit/wardrobe_check.py --outfits 300 --sheet 100 --seed 1

Composes `--outfits` random outfits in every pose and frame
(`game_data.scenes.players.coverage`) and prints the share that composes, then
the failures grouped by item. Then draws `--sheet` random players
(`Wardrobe.draw`) onto one contact sheet, each labelled with its pose and
weapon type, its box outlined with `--boxes`, and prints the items `draw`
redrew. Writes `coverage.txt` and `players.png` under `--out`. Needs an
extraction; no client, and it sends no input.
"""

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

from game_data.catalogue import Catalogue
from game_data.config import STORE
from game_data.scenes import Look, Player, Wardrobe, coverage
from game_data.scenes.players import slot_of, summary

CELL = (180, 160)
"""A contact sheet cell's width and height, in pixels."""

CAPTION = 14
"""The caption's height under each cell."""

BACKGROUND = (236, 236, 236)
"""The sheet's colour, BGR."""


def cell(player: Player, look: Look, *, boxes: bool) -> np.ndarray:
    """One player on a cell of `CELL`, feet near the bottom, captioned."""
    width, height = CELL
    out = np.full((height + CAPTION, width, 3), BACKGROUND, dtype=np.uint8)
    x1, y1, x2, y2 = player.box
    ox, oy = player.origin
    crop = player.pixels[y1:y2, x1:x2]
    left = width // 2 - (ox - x1)
    top = height - 10 - (oy - y1)
    _over(out, crop, left, top)
    if boxes:
        cv2.rectangle(
            out, (left, top), (left + x2 - x1 - 1, top + y2 - y1 - 1), (0, 160, 0), 1
        )
    kind = look.outfit.wields
    caption = f"{look.action}/{look.frame} {kind.name if kind else 'bare'}"
    cv2.putText(
        out,
        caption,
        (3, height + CAPTION - 4),
        cv2.FONT_HERSHEY_PLAIN,
        0.75,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    return out


def _over(target: np.ndarray, rgba: np.ndarray, left: int, top: int) -> None:
    """Lays RGBA pixels over a BGR image, clipped to it."""
    height, width = target.shape[:2]
    x0, y0 = max(left, 0), max(top, 0)
    x1 = min(left + rgba.shape[1], width)
    y1 = min(top + rgba.shape[0], height)
    if x0 >= x1 or y0 >= y1:
        return
    src = rgba[y0 - top : y1 - top, x0 - left : x1 - left].astype(np.float32)
    alpha = src[..., 3:] / 255
    region = target[y0:y1, x0:x1].astype(np.float32)
    bgr = src[..., 2::-1]
    target[y0:y1, x0:x1] = np.rint(bgr * alpha + region * (1 - alpha)).astype(np.uint8)


def sheet(cells: list[np.ndarray]) -> np.ndarray:
    """The cells in a near-square grid."""
    columns = math.ceil(math.sqrt(len(cells)))
    rows = math.ceil(len(cells) / columns)
    height, width = cells[0].shape[:2]
    out = np.full((rows * height, columns * width, 3), BACKGROUND, dtype=np.uint8)
    for index, found in enumerate(cells):
        row, column = divmod(index, columns)
        out[
            row * height : (row + 1) * height, column * width : (column + 1) * width
        ] = found
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outfits", type=int, default=300)
    parser.add_argument("--sheet", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--boxes", action="store_true", help="outline each box")
    parser.add_argument("--out", type=Path, default=STORE / "renders" / "672-wardrobe")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with Catalogue.latest() as cat, Wardrobe(cat) as wardrobe:
        report = summary(
            coverage(wardrobe, np.random.default_rng(args.seed), args.outfits)
        )
        print(report)
        rng = np.random.default_rng(args.seed)
        cells = []
        for _ in range(args.sheet):
            look = wardrobe.draw(rng)
            player = wardrobe.compose(
                look.outfit, look.action, look.frame, flip=look.flip
            )
            cells.append(cell(player, look, boxes=args.boxes))
        misses = wardrobe.misses
        redrawn = "\n".join(
            [f"draw redrew {sum(misses.values())} players; by item:"]
            + [f"  {item} ({slot_of(item)}): x{n}" for item, n in misses.most_common()]
        )
        print(redrawn)

    (args.out / "coverage.txt").write_text(f"{report}\n{redrawn}\n", encoding="utf-8")
    image = args.out / "players.png"
    if not cv2.imwrite(str(image), sheet(cells)):
        raise SystemExit(f"could not write {image}")
    print(f"wrote {image}")
