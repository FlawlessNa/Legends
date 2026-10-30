"""`python -m ml_training synth`, on `test_scenes`' synthetic client."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from game_data.catalogue import build_catalogue
from game_data.extraction import extract
from game_data.scenes import SCENES_VERSION
from ml_training.__main__ import main
from ml_training.synthetic import SynthError, synth
from ml_training.synthetic import command as module
from tests.test_game_data.test_scenes import FIELD, TWINS, write_scenes_client

CLASSES = ["Bat", "Block", "Crab"]
SMALL_CLIENT = {"client": [200, 100], "mobs": [2, 4]}


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("synth")
    extract(
        write_scenes_client(base / "Data"), base / "store", catalogue=build_catalogue
    )
    return base / "store"


@pytest.fixture(autouse=True)
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(module, "DATASETS", tmp_path / "datasets")
    monkeypatch.setattr(module, "PRODUCTION", tmp_path / "production")
    monkeypatch.setattr(module, "RUNS", tmp_path / "runs")
    return tmp_path


class Trainer:
    """Stands in for training: writes a `best.pt`, and records what it got."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Mapping[str, Any], str]] = []

    def __call__(self, data_yaml: Path, settings: Mapping[str, Any], run: str) -> Path:
        self.calls.append((data_yaml, settings, run))
        best = module.RUNS / run / "weights" / "best.pt"
        best.parent.mkdir(parents=True, exist_ok=True)
        best.write_bytes(b"weights")
        return best


def write_recipe(path: Path, **values: object) -> Path:
    recipe = {
        "scenes_version": SCENES_VERSION,
        "compose_scene": SMALL_CLIENT,
        "seed": 5,
        "count": 6,
    } | values
    path.write_text(json.dumps(recipe), encoding="utf-8")
    return path


def run(
    store: Path,
    tmp: Path,
    trainer: Trainer,
    *,
    name: str | None = None,
    count: int | None = None,
    seed: int | None = None,
    keep_dataset: bool = False,
) -> Path:
    recipe = write_recipe(tmp / "start.json")
    return synth(
        FIELD,
        recipe=recipe,
        root=store,
        trainer=trainer,
        name=name,
        count=count,
        seed=seed,
        keep_dataset=keep_dataset,
    )


def hashes(folder: Path) -> dict[str, str]:
    return {
        f"{p.parent.name}/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.suffix in (".jpg", ".txt") and p.parent.parent.name in ("images", "labels")
    }


def test_it_writes_weights_recipe_and_samples_and_no_dataset(
    store: Path, data: Path
) -> None:
    trainer = Trainer()
    folder = run(store, data, trainer)

    assert folder == data / "production" / str(FIELD)
    assert (folder / "weights" / "best.pt").read_bytes() == b"weights"
    assert len(list((folder / "samples").glob("*.png"))) == 6
    assert list((data / "datasets").iterdir()) == []
    recipe = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
    assert recipe["classes"] == CLASSES
    assert recipe["map_id"] == FIELD
    assert recipe["map_name"] == "Field"
    assert recipe["scenes_version"] == SCENES_VERSION
    assert (recipe["seed"], recipe["count"]) == (5, 6)
    assert recipe["compose_scene"]["client"] == [200, 100]
    assert recipe["final_training"]["epochs"] == 100
    assert {"build", "ultralytics", "torch"} <= recipe.keys()


def test_it_trains_on_a_dataset_split_85_15_with_sorted_classes(
    store: Path, data: Path
) -> None:
    trainer = Trainer()
    synth(
        FIELD,
        recipe=write_recipe(data / "r.json", count=20),
        root=store,
        trainer=trainer,
        keep_dataset=True,
    )

    dataset = data / "datasets" / f"synth_{FIELD}"
    assert len(list((dataset / "images" / "train").glob("*.jpg"))) == 17
    assert len(list((dataset / "images" / "val").glob("*.jpg"))) == 3
    assert f"- {CLASSES[0]}" in (dataset / "data.yaml").read_text(encoding="utf-8")
    assert not (data / "datasets" / f"synth_{FIELD}_scenes").exists()


def test_rerunning_from_the_recipe_gives_the_same_dataset(
    store: Path, data: Path
) -> None:
    first = run(store, data, Trainer(), name="a", keep_dataset=True)
    again = synth(
        None,
        recipe=first / "recipe.json",
        name="b",
        root=store,
        trainer=Trainer(),
        keep_dataset=True,
    )

    before, after = (
        hashes(data / "datasets" / "synth_a"),
        hashes(data / "datasets" / "synth_b"),
    )
    assert len(before) == 12
    assert before == after
    assert (again / "recipe.json").read_text() == (first / "recipe.json").read_text()


def test_flags_override_the_recipe(store: Path, data: Path) -> None:
    folder = run(store, data, Trainer(), count=3, seed=9)

    recipe = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
    assert (recipe["seed"], recipe["count"]) == (9, 3)


def test_a_drawn_seed_is_printed_and_recorded(
    store: Path, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = synth(
        FIELD,
        count=1,
        root=store,
        trainer=Trainer(),
        training={"epochs": 1},
    )

    seed = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))["seed"]
    assert f"seed {seed} (drawn)" in capsys.readouterr().out


def test_it_prints_the_folder_and_the_mobs_list(
    store: Path, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = run(store, data, Trainer())

    out = capsys.readouterr().out
    assert str(folder) in out
    assert json.dumps(CLASSES) in out


def test_a_name_is_shared_only_by_equal_classes(store: Path, data: Path) -> None:
    other = data / "production" / "shared"
    other.mkdir(parents=True)
    (other / "recipe.json").write_text('{"classes": ["Snail"]}', encoding="utf-8")

    with pytest.raises(SynthError, match="other classes"):
        synth(FIELD, count=1, name="shared", root=store, trainer=Trainer())

    run(store, data, Trainer(), name="same")
    run(store, data, Trainer(), name="same")


def test_no_map_is_an_error(store: Path) -> None:
    with pytest.raises(SynthError, match="name a map"):
        synth(None, root=store, trainer=Trainer())


def test_an_unknown_map_exits_1_with_the_catalogues_message(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["synth", "Nowhere At All", "--root", str(store)]) == 1
    assert "no map is named 'Nowhere At All'" in capsys.readouterr().err


def test_two_species_of_one_name_exit_1(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["synth", str(TWINS), "--root", str(store)]) == 1
    assert "share the class name" in capsys.readouterr().err


@pytest.mark.system
def test_one_epoch_of_real_training(store: Path, data: Path) -> None:
    folder = synth(
        FIELD,
        recipe=write_recipe(data / "r.json", count=8),
        root=store,
        training={"epochs": 1, "batch_size": 2, "workers": 0},
    )

    assert (folder / "weights" / "best.pt").is_file()
    assert list((data / "datasets").iterdir()) == []
