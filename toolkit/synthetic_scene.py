"""Compose one synthetic client screen of a map and save it with its labels.

    python toolkit/synthetic_scene.py "Damp Forest" --seed 42 --out scene.png

Needs an extraction (`python -m game_data extract`).
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from game_data.catalogue import Catalogue
from game_data.scenes import compose_scene

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", help="a map's name, or its ID")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("scene.png"))
    parser.add_argument("--boxes", action="store_true", help="draw the labels")
    parser.add_argument("--no-occluders", action="store_true")
    args = parser.parse_args()

    with Catalogue.latest() as cat:
        scene = compose_scene(
            cat,
            args.map,
            np.random.default_rng(args.seed),
            occluders=None
            if args.no_occluders
            else {"drops": (0, 8), "damage": (0, 4)},
        )

    img = cv2.cvtColor(scene.image, cv2.COLOR_RGB2BGR)
    for label in scene.labels:
        print(label)
        if args.boxes:
            x1, y1, x2, y2 = (int(v) for v in label.box)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 1)
            cv2.putText(
                img,
                label.cls,
                (x1, max(y1 - 3, 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.out), img):
        raise SystemExit(f"could not write {args.out}")
    print(f"wrote {args.out.resolve()}")
