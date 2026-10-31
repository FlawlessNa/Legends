"""The live viewer's recorder, model-folder resolution, and `score`."""

from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from ml_training.__main__ import main
from ml_training.model_manager import recording
from ml_training.model_manager.recording import FrameRecorder, resolve_model, score
from ml_training.model_manager.trainer import YOLOTrainer


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_recorder(tmp_path: Path, clock: Clock) -> FrameRecorder:
    return FrameRecorder(
        "mymodel", ["Character", "Slime"], interval=3, root=tmp_path, clock=clock
    )


FRAME = np.zeros((100, 200, 3), dtype=np.uint8)


def test_recorder_writes_nothing_when_off(tmp_path: Path, clock: Clock) -> None:
    rec = make_recorder(tmp_path, clock)
    assert rec.record(FRAME, [(0, (0, 0, 10, 10))]) is None
    assert list(tmp_path.iterdir()) == []


def test_recorder_writes_image_and_label_per_interval(
    tmp_path: Path, clock: Clock
) -> None:
    rec = make_recorder(tmp_path, clock)
    rec.enabled = True

    assert rec.record(FRAME, [(1, (20, 10, 60, 50))]) is not None
    clock.now = 1
    assert rec.record(FRAME, []) is None  # inside the interval
    clock.now = 3
    assert rec.record(FRAME, []) is not None

    folder = rec.directory
    assert folder is not None
    assert folder.parent == tmp_path / "mymodel"
    assert len(list((folder / "images").glob("*.png"))) == 2
    assert len(list((folder / "labels").glob("*.txt"))) == 2
    assert (folder / "classes.txt").read_text().split() == ["Character", "Slime"]
    first = (folder / "labels" / "000000.txt").read_text().split()
    assert first == ["1", "0.200000", "0.300000", "0.200000", "0.400000"]
    assert (folder / "labels" / "000001.txt").read_text() == ""


def test_resolve_folder_with_recipe(tmp_path: Path) -> None:
    (tmp_path / "m" / "weights").mkdir(parents=True)
    (tmp_path / "m" / "recipe.json").write_text('{"classes": ["A", "B"]}')
    weights, name, classes = resolve_model(tmp_path / "m")
    assert (weights, name, classes) == (
        tmp_path / "m" / "weights" / "best.pt",
        "m",
        ["A", "B"],
    )


def test_resolve_weights_path_names(tmp_path: Path) -> None:
    inside = tmp_path / "m" / "weights" / "best.pt"
    assert resolve_model(inside)[1:] == ("m", None)
    assert resolve_model(tmp_path / "loose.pt")[1:] == ("loose", None)


def make_recording(root: Path) -> Path:
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir()
    (root / "classes.txt").write_text("Character\nSlime\n")
    return root


def test_score_prints_three_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make_recording(tmp_path / "rec")
    seen = {}

    def evaluate(weights: Path, data_yaml: Path) -> dict:
        seen["data"] = data_yaml.read_text()
        return {"precision": 0.5, "recall": 0.25, "mAP50": 0.75, "mAP50-95": 0.1}

    metrics = score(tmp_path / "m", rec, evaluate)

    assert metrics == {"precision": 0.5, "recall": 0.25, "mAP50": 0.75}
    assert "Slime" in seen["data"]
    assert "images" in seen["data"]


def test_score_command_uses_trainer_evaluate(
    tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make_recording(tmp_path / "rec")
    mocker.patch.object(YOLOTrainer, "__init__", return_value=None)
    evaluate = mocker.patch.object(
        YOLOTrainer,
        "evaluate",
        return_value={"precision": 0.5, "recall": 0.25, "mAP50": 0.75},
    )

    assert main(["score", str(tmp_path / "m"), str(rec)]) == 0

    out = capsys.readouterr().out
    assert "0.500" in out
    assert "0.250" in out
    assert "0.750" in out
    assert evaluate.call_args.args[0] == str(rec / "data.yaml")


def test_score_uses_newest_recording_of_a_model(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    mocker.patch.object(recording, "RECORDINGS_ROOT", tmp_path)
    make_recording(tmp_path / "m" / "2026-01-01_000000")
    newest = make_recording(tmp_path / "m" / "2026-02-01_000000")
    mocker.patch.object(recording, "latest_recording", return_value=newest)
    got: list[Path] = []

    def evaluate(weights: Path, data_yaml: Path) -> dict:
        got.append(data_yaml)
        return {"precision": 1, "recall": 1, "mAP50": 1}

    score("m", "m", evaluate)
    assert got[0].parent == newest
