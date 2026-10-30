"""
`synth`: generates a dataset of scenes for a map, trains a model on it, writes
the model with its recipe and samples where the bot looks for it, and deletes
the dataset.

The model lands in `ml_training/data/models/production/<NAME>/`:
`weights/best.pt`, `recipe.json` and `samples/`. The recipe holds every value
the run used, so that `--recipe` alone generates the same dataset again. The
weights are not reproduced: training isn't deterministic.
"""

import json
import random
import secrets
import shutil
import sys
from collections.abc import Callable, Mapping
from importlib import metadata
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

from game_data.catalogue import Catalogue
from game_data.config import REPO, STORE
from game_data.render import VIEWPORT
from game_data.scenes import (
    MOBS,
    SCENES_VERSION,
    VISIBILITY_FLOOR,
    Scene,
    compose_scene,
    map_classes,
)

from ..config import config
from ..dataset_manager.dataset import YOLODataset
from ..model_manager.trainer import YOLOTrainer

DATA: Final = Path(__file__).resolve().parent.parent / "data"
DATASETS: Final = DATA / "datasets"
PRODUCTION: Final = DATA / "models" / "production"
RUNS: Final = DATA / "models" / "runs"

COUNT: Final = 3000
TRAIN_SPLIT: Final = 0.85
SAMPLES: Final = 20
JPEG_QUALITY: Final = 95

Trainer = Callable[[Path, Mapping[str, Any], str], Path]
"""Trains on a `data.yaml` with the settings, under a run name; returns `best.pt`."""


class SynthError(Exception):
    """The command can't run as asked."""


def final_training() -> dict[str, Any]:
    """The `final_training` settings of `settings.yaml`."""
    return dict(config.get("model.final_training", {}))


def train_final(data_yaml: Path, settings: Mapping[str, Any], run: str) -> Path:
    """Trains from the repo's local base model, and returns the run's `best.pt`."""
    base = REPO / str(config.get("model.base_model"))
    if not base.is_file():
        raise SynthError(f"the base model {base} is missing; it isn't downloaded")
    rest = {
        key: value
        for key, value in settings.items()
        if key not in ("epochs", "batch_size", "patience")
    }
    trainer = YOLOTrainer(base_model=str(base))
    trainer.train(
        str(data_yaml),
        epochs=settings["epochs"],
        batch_size=settings["batch_size"],
        patience=settings["patience"],
        project=str(RUNS),
        name=run,
        **rest,
    )
    return Path(trainer.model.trainer.save_dir) / "weights" / "best.pt"


def synth(
    map: str | int | None,
    *,
    count: int | None = None,
    seed: int | None = None,
    build: str | None = None,
    name: str | None = None,
    recipe: Path | None = None,
    keep_dataset: bool = False,
    root: Path = STORE,
    trainer: Trainer = train_final,
    training: Mapping[str, Any] | None = None,
) -> Path:
    """
    Runs the command and returns the model's folder.

    :param map: A map's name or ID; the recipe's when `None`.
    :param recipe: A `recipe.json`; what it holds is used, and the other
        arguments override it.
    :param training: Overrides the `final_training` settings, a test's way to
        train one epoch.
    :raises SynthError: Nothing says which map, or a model of that name has
        other classes.
    :raises LookupError: As `Catalogue.map` does.
    """
    read: dict[str, Any] = (
        json.loads(recipe.read_text(encoding="utf-8")) if recipe else {}
    )
    if read and read.get("scenes_version") != SCENES_VERSION:
        print(
            f"warning: the recipe is of scenes version {read.get('scenes_version')}, "
            f"this is {SCENES_VERSION}: the dataset will differ",
            file=sys.stderr,
        )
    which = map if map is not None else read.get("map_id")
    if which is None:
        raise SynthError("name a map, or give a --recipe that has one")
    total: int = count if count is not None else read.get("count", COUNT)
    if total < 1:
        raise SynthError(f"--count must be positive, not {total}")
    if seed is None:
        seed = read.get("seed")
    if seed is None:
        seed = secrets.randbits(32)
        print(f"seed {seed} (drawn)")
    build = build or read.get("build")
    given = read.get("compose_scene", {})
    compose: dict[str, Any] = {
        "client": tuple(given.get("client", VIEWPORT)),
        "mobs": tuple(given.get("mobs", MOBS)),
        "visibility_floor": given.get("visibility_floor", VISIBILITY_FLOOR),
        "cameras": given.get("cameras"),
    }
    settings = {**(read.get("final_training") or final_training()), **(training or {})}

    with Catalogue.open(build, root) if build else Catalogue.latest(root) as cat:
        found = cat.map(which)
        classes = map_classes(cat, found.id)
        if not classes:
            raise SynthError(f"map {found.id} has no mob to detect")
        label = found.name or str(found.id)
        name = name or str(found.id)
        folder = PRODUCTION / name
        _check_shared(folder, classes)
        print(f"{label} ({found.id}), build {cat.build}: {len(classes)} classes")

        stage = DATASETS / f"synth_{name}_scenes"
        dataset = YOLODataset(f"synth_{name}", classes, str(DATASETS))
        print(f"generating {total} scenes")
        _generate(cat, found.id, classes, total, seed, compose, stage, folder)
        print("building the dataset")
        _split(dataset, stage, seed)
        shutil.rmtree(stage)
        manifest = {
            "build": cat.build,
            "map_id": found.id,
            "map_name": found.name,
            "scenes_version": SCENES_VERSION,
            "seed": seed,
            "count": total,
            "compose_scene": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in compose.items()
            },
            "classes": classes,
            "final_training": settings,
            "ultralytics": metadata.version("ultralytics"),
            "torch": metadata.version("torch"),
        }

    try:
        print("training")
        best = trainer(Path(dataset.get_data_yaml_path()), settings, f"synth_{name}")
        (folder / "weights").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best, folder / "weights" / "best.pt")
        (folder / "recipe.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    finally:
        if not keep_dataset:
            shutil.rmtree(dataset.dataset_path, ignore_errors=True)
    print(f"model: {folder}")
    print("mobs for configs/maps/<map>.json:")
    print(json.dumps(classes))
    return folder


def _check_shared(folder: Path, classes: list[str]) -> None:
    """A model folder that already exists is shared only by equal classes."""
    existing = folder / "recipe.json"
    if not existing.is_file():
        return
    had = json.loads(existing.read_text(encoding="utf-8")).get("classes")
    if had is not None and had != classes:
        raise SynthError(
            f"{folder} is a model of other classes ({had}); give --name another "
            "name, or reuse one only for a map with the same mobs"
        )


def _generate(
    cat: Catalogue,
    map_id: int,
    classes: list[str],
    count: int,
    seed: int,
    compose: Mapping[str, Any],
    stage: Path,
    folder: Path,
) -> None:
    """Writes `count` scenes and YOLO labels to `stage`, and samples to `folder`."""
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "images").mkdir(parents=True)
    (stage / "labels").mkdir()
    samples = folder / "samples"
    if samples.exists():
        shutil.rmtree(samples)
    samples.mkdir(parents=True)
    rng = np.random.default_rng(seed)
    ids = {cls: n for n, cls in enumerate(classes)}
    for n in range(count):
        scene = compose_scene(cat, map_id, rng, **compose)
        stem = f"{n:05d}"
        _write_image(stage / "images" / f"{stem}.jpg", scene.image)
        (stage / "labels" / f"{stem}.txt").write_text(
            _yolo(scene, ids), encoding="utf-8"
        )
        if n < min(SAMPLES, count):
            _write_image(samples / f"{stem}.png", _drawn(scene))
        if (n + 1) % 100 == 0 or n + 1 == count:
            print(f"\r{n + 1}/{count} scenes", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)


def _write_image(path: Path, rgb: np.ndarray) -> None:
    params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY] if path.suffix == ".jpg" else []
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), params):
        raise SynthError(f"couldn't write {path}")


def _yolo(scene: Scene, ids: Mapping[str, int]) -> str:
    height, width = scene.image.shape[:2]
    lines = []
    for label in scene.labels:
        x1, y1, x2, y2 = label.box
        lines.append(
            f"{ids[label.cls]} {(x1 + x2) / 2 / width:.6f} "
            f"{(y1 + y2) / 2 / height:.6f} {(x2 - x1) / width:.6f} "
            f"{(y2 - y1) / height:.6f}\n"
        )
    return "".join(lines)


def _drawn(scene: Scene) -> np.ndarray:
    image = scene.image.copy()
    for label in scene.labels:
        x1, y1, x2, y2 = label.box
        cv2.rectangle(image, (x1, y1), (x2 - 1, y2 - 1), (255, 0, 0), 2)
        cv2.putText(
            image,
            f"{label.cls} {label.visible:.2f}",
            (x1, max(y1 - 4, 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            1,
        )
    return image


def _split(dataset: YOLODataset, stage: Path, seed: int) -> None:
    """Builds the dataset from `stage`, its random split seeded by the run's."""
    state = random.getstate()
    random.seed(seed)
    try:
        dataset.create(str(stage / "images"), str(stage / "labels"), TRAIN_SPLIT)
    finally:
        random.setstate(state)
