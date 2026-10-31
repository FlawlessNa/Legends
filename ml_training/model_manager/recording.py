"""Model folders, live-viewer recordings, and scoring a model on a recording.

Nothing here needs Qt or a game window.
"""

import json
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

RECORDINGS_ROOT = Path(__file__).resolve().parent.parent / "data" / "recordings"
DEFAULT_INTERVAL_S = 3.0


def resolve_model(model_path: str | Path) -> tuple[Path, str, list[str] | None]:
    """
    Resolve a model folder or a weights path.

    Returns (weights, model name, classes from recipe.json or None). A folder is
    read as `<folder>/weights/best.pt`, named after the folder. A weights path is
    named after the folder above `weights/`, else after the file's stem.
    """
    path = Path(model_path)
    if path.is_dir():
        weights, folder = path / "weights" / "best.pt", path
    else:
        weights = path
        folder = path.parent.parent if path.parent.name == "weights" else None

    name = folder.name if folder is not None else path.stem
    recipe = (folder / "recipe.json") if folder is not None else None
    classes = None
    if recipe is not None and recipe.is_file():
        classes = list(json.loads(recipe.read_text(encoding="utf-8"))["classes"])
    return weights, name, classes


def _yolo_line(cls_id: int, box: Sequence[float], width: int, height: int) -> str:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
    w, h = (x2 - x1) / width, (y2 - y1) / height
    return f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


class FrameRecorder:
    """Saves a frame and its detections every `interval` seconds while `enabled`."""

    def __init__(
        self,
        model_name: str,
        classes: Sequence[str],
        interval: float = DEFAULT_INTERVAL_S,
        root: Path = RECORDINGS_ROOT,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.model_name = model_name
        self.classes = list(classes)
        self.interval = interval
        self.enabled = False
        self.saved = 0
        self._root = Path(root)
        self._clock = clock
        self._last: float | None = None
        self._dir: Path | None = None

    @property
    def directory(self) -> Path | None:
        """The current recording's folder, or None before the first save."""
        return self._dir

    def _open(self) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        directory = self._root / self.model_name / stamp
        (directory / "images").mkdir(parents=True, exist_ok=True)
        (directory / "labels").mkdir(exist_ok=True)
        (directory / "classes.txt").write_text(
            "\n".join(self.classes) + "\n", encoding="utf-8"
        )
        return directory

    def record(
        self, frame: np.ndarray, detections: Sequence[tuple[int, Sequence[float]]]
    ) -> Path | None:
        """
        Save `frame` (as the model saw it) and `detections`, a sequence of
        (class id, (x1, y1, x2, y2) in pixels). Returns the image path, or None
        when off or inside the interval.
        """
        if not self.enabled:
            return None
        now = self._clock()
        if self._last is not None and now - self._last < self.interval:
            return None
        self._last = now

        if self._dir is None:
            self._dir = self._open()
        height, width = frame.shape[:2]
        stem = f"{self.saved:06d}"
        image = self._dir / "images" / f"{stem}.png"
        cv2.imwrite(str(image), frame)
        lines = [_yolo_line(c, box, width, height) for c, box in detections]
        (self._dir / "labels" / f"{stem}.txt").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8"
        )
        self.saved += 1
        return image


def latest_recording(model_name: str, root: Path = RECORDINGS_ROOT) -> Path:
    """The newest recording of `model_name`."""
    runs = sorted(p for p in (Path(root) / model_name).glob("*") if p.is_dir())
    if not runs:
        raise FileNotFoundError(f"No recordings of {model_name!r} under {root}")
    return runs[-1]


def recording_data_yaml(recording: Path) -> Path:
    """Write the data.yaml that points YOLO at a recording, and return it."""
    recording = Path(recording)
    classes_file = recording / "classes.txt"
    if not (recording / "images").is_dir() or not classes_file.is_file():
        raise FileNotFoundError(
            f"{recording} is not a recording: it needs images/ and classes.txt"
        )
    classes = [c for c in classes_file.read_text(encoding="utf-8").splitlines() if c]
    data = {
        "path": str(recording.resolve()),
        "train": "images",
        "val": "images",
        "nc": len(classes),
        "names": classes,
    }
    target = recording / "data.yaml"
    target.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    return target


def score(
    model: str | Path,
    recording: str | Path,
    evaluate: Callable[[Path, Path], dict] | None = None,
) -> dict[str, float]:
    """
    Precision, recall and mAP50 of `model` on a recording's corrected labels.

    `evaluate(weights, data_yaml)` returns `YOLOTrainer.evaluate`'s metrics; the
    default builds a `YOLOTrainer` on the weights. `recording` is a folder, or
    the name of a model whose newest recording is used.
    """
    weights, _, _ = resolve_model(model)
    recording = Path(recording)
    if not recording.is_dir():
        recording = latest_recording(str(recording))
    data_yaml = recording_data_yaml(recording)

    if evaluate is None:

        def evaluate(weights: Path, data_yaml: Path) -> dict:
            from .trainer import YOLOTrainer

            return YOLOTrainer(base_model=str(weights)).evaluate(
                str(data_yaml), split="val"
            )

    metrics = evaluate(weights, data_yaml)
    return {k: float(metrics[k]) for k in ("precision", "recall", "mAP50")}
