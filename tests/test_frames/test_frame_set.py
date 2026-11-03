"""The frame set's expected-readings loader, on committed files and on bad ones."""

import copy
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from botting.screen import Status
from tests import frame_set
from tests.frame_set import FrameSetError, FrameSetMissing

GOOD: dict[str, Any] = {
    "frames": [
        {
            "file": "a.png",
            "client_size": [1024, 768],
            "notes": "full bar",
            "expect": {
                "status_bar": {"status": "read", "value": {"hp": 10}},
                "minimap": {"status": "absent", "value": None},
            },
        }
    ]
}


def broken(**changes: object) -> dict[str, Any]:
    raw = copy.deepcopy(GOOD)
    raw["frames"][0].update(changes)
    return raw


@pytest.mark.parametrize("path", frame_set.committed_files(), ids=lambda p: p.name)
def test_every_committed_file_is_valid(path: Path) -> None:
    frame_set.load_expected(path)


def test_current_tag_is_named() -> None:
    assert frame_set.current_tag()


def test_a_valid_file_parses() -> None:
    (entry,) = frame_set.parse_entries(GOOD, "good")
    assert entry.client_size == (1024, 768)
    assert entry.expect["status_bar"].status is Status.READ
    assert entry.expect["status_bar"].value == {"hp": 10}
    assert entry.expect["minimap"].status is Status.ABSENT


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({}, "frames"),
        (broken(file="a.jpg"), "png"),
        (broken(client_size=[0, 5]), "client_size"),
        (broken(client_size=[1, 2, 3]), "client_size"),
        (broken(notes=3), "notes"),
        (broken(expect={}), "stub"),
        (broken(expect={"r": {"status": "nope", "value": None}}), "not one of"),
        (broken(expect={"r": {"status": "read", "value": None}}), "needs a value"),
        (broken(expect={"r": {"status": "absent", "value": 3}}), "carries no value"),
        (broken(expect={"r": {"status": "read"}}), "status and value"),
    ],
)
def test_a_malformed_file_is_refused(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(FrameSetError, match=message):
        frame_set.parse_entries(raw, "bad")


def test_a_frame_listed_twice_is_refused() -> None:
    raw = copy.deepcopy(GOOD)
    raw["frames"].append(copy.deepcopy(raw["frames"][0]))
    with pytest.raises(FrameSetError, match="twice"):
        frame_set.parse_entries(raw, "bad")


def test_missing_frames_say_how_to_fetch_them(tmp_path: Path) -> None:
    with pytest.raises(FrameSetMissing, match=r"scripts/fetch_frames.py v1"):
        frame_set.open_frame_set("v1", tmp_path)


def test_a_frame_set_on_disk_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    readings = tmp_path / "readings"
    readings.mkdir()
    (readings / "t.json").write_text(json.dumps(GOOD), encoding="utf-8")
    monkeypatch.setattr(frame_set, "TESTS_FRAMES", readings)
    folder = tmp_path / "data" / "t"
    folder.mkdir(parents=True)

    with pytest.raises(FrameSetMissing, match="lacks 1 frame"):
        frame_set.open_frame_set("t", tmp_path / "data")

    cv2.imwrite(str(folder / "a.png"), np.zeros((4, 6, 3), np.uint8))
    opened = frame_set.open_frame_set("t", tmp_path / "data")
    assert opened.pixels(opened.entries[0]).shape == (4, 6, 3)
