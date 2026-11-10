"""
`toolkit/position_check.py` on synthetic readings: its rows, its rates, the
frames it saves and the order it replays in. The real frame set is
`test_position_check_frames.py`'s.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from botting.screen import Frame, Reading
from botting.utilities import Box
from maple.model.world import MinimapTransform
from maple.screen.minimap import MinimapState, MinimapView
from maple.screen.position import Camera, CharacterSighting
from toolkit import position_check as tool

REPO = Path(__file__).resolve().parents[2]
TRANSFORM = MinimapTransform(centre=(1000, 2000), mag=4)
MARKER = (100, 140)
"""The minimap's feet position is (608, 344) virtual (`test_position_fusion`)."""
FEET = (608, 344)
CAMERA = Camera(200, 50, 0.9, 3.0, (1366, 768))
AT = 5.0


def screen(ok: bool = True, at: float = AT) -> Frame:
    reason = "" if ok else "window 1 wasn't in front before the copy (2 was)"
    return Frame(np.zeros((768, 1366, 3), np.uint8), (1366, 768), at, True, ok, reason)


class Minimap:
    def __init__(self, marker: Reading[tuple[int, int]] | None = None) -> None:
        self.marker = marker or Reading.read(MARKER, AT)
        self.frames: list[Frame] = []

    def read(self, frame: Frame) -> Reading[MinimapView]:
        self.frames.append(frame)
        view = MinimapView(
            MinimapState.EXPANDED,
            Box(left=10, right=180, top=40, bottom=150),
            Box(left=0, right=190, top=0, bottom=160),
            self.marker,
        )
        return Reading.read(view, frame.captured_at)


class Cameras:
    def __init__(self, reading: Reading[Camera]) -> None:
        self.reading = reading
        self.made = 0

    def read(self, frame: Frame, seed: Camera | None = None) -> Reading[Camera]:
        return self.reading


class Finder:
    def __init__(self, *feet: tuple[float, float], own: int | None = None) -> None:
        self.sightings = [
            CharacterSighting((x - CAMERA.x, y - CAMERA.y), "name tag", 0.9, i == own)
            for i, (x, y) in enumerate(feet)
        ]
        self.knows = own is not None

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        return Reading.read(self.sightings, frame.captured_at)

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        return self.knows


def readers(
    finder: Finder,
    camera: Reading[Camera] | None = None,
    minimap: Minimap | None = None,
) -> tuple[tool.MapReaders, Cameras]:
    cameras = Cameras(camera or Reading.read(CAMERA, AT))

    def make() -> Cameras:
        cameras.made += 1
        return cameras

    built = tool.MapReaders(
        10002000, minimap or Minimap(), TRANSFORM, make, tool.FinderTap(finder)
    )
    return built, cameras


def test_a_fused_frame_records_every_read_and_how_far_apart_they_are() -> None:
    built, _ = readers(Finder((611.5, 340), (900, 344)))

    r = tool.row(built.read(screen(), name="f1", still=True), start=AT - 2)

    assert set(r) == set(tool.FIELDS)
    assert (r["frame"], r["map_id"], r["frame_ok"], r["still"]) == (
        "f1",
        "10002000",
        "1",
        "1",
    )
    assert r["captured_at"] == "2.000"
    assert (r["minimap_status"], r["marker_x"], r["marker_y"]) == ("read", "100", "140")
    assert (r["minimap_x"], r["minimap_y"]) == ("608", "344")
    assert (r["camera_status"], r["camera_x"], r["camera_y"]) == ("read", "200", "50")
    assert (r["camera_share"], r["play_area_width"]) == ("0.900", "1366")
    assert (r["characters_status"], r["characters_found"]) == ("read", "2")
    assert r["sightings"] == "611.5:340.0;900.0:344.0"
    assert (r["position_status"], r["position_source"]) == ("read", "fused")
    assert (r["position_x"], r["position_y"]) == ("611.5", "340.0")
    assert (r["play_x"], r["play_dx"], r["play_dy"]) == ("611.5", "3.5", "-4.0")
    assert (r["near"], r["by_tag"], r["own_elsewhere"]) == ("1", "0", "0")
    assert float(r["age_ms"]) >= 0


def test_a_camera_fusion_doesnt_get_skips_the_characters_and_falls_back() -> None:
    built, _ = readers(Finder((611.5, 340)), Reading.unsure(AT, "another map"))

    r = tool.row(built.read(screen()))

    assert (r["camera_status"], r["camera_detail"]) == ("unsure", "another map")
    assert (r["characters_status"], r["characters_detail"]) == (
        tool.SKIPPED,
        "not asked",
    )
    assert (r["position_status"], r["position_source"]) == ("read", "coarse")
    assert (r["play_x"], r["play_dx"]) == ("", "")


def test_no_minimap_position_asks_nothing_else_and_is_unsure() -> None:
    marker: Reading[tuple[int, int]] = Reading.covered(AT, "under the cursor")
    built, cameras = readers(Finder((611.5, 340)), minimap=Minimap(marker))

    r = tool.row(built.read(screen()))

    assert (r["minimap_status"], r["minimap_detail"]) == ("covered", "under the cursor")
    assert (r["minimap_x"], r["camera_status"]) == ("", tool.SKIPPED)
    assert r["characters_status"] == tool.SKIPPED
    assert r["position_status"] == "unsure"
    assert cameras.made == 0


def test_two_characters_by_the_minimaps_are_unsure_and_the_nearest_is_shown() -> None:
    built, _ = readers(Finder((620, 344), (600, 340)))

    r = tool.row(built.read(screen()))

    assert (r["position_status"], r["near"]) == ("unsure", "2")
    assert (r["play_x"], r["play_y"]) == ("600.0", "340.0")


def test_our_tag_outside_the_window_is_the_play_area_read_and_flagged() -> None:
    built, _ = readers(Finder((900, 344), (611, 344), own=0))

    r = tool.row(built.read(screen()))

    assert (r["position_status"], r["position_source"]) == ("read", "coarse")
    assert (r["by_tag"], r["own_elsewhere"]) == ("1", "1")
    assert r["sightings"] == "900.0:344.0:own;611.0:344.0"
    assert (r["play_x"], r["play_dx"]) == ("900.0", "292.0")


def test_the_minimap_can_be_read_on_an_older_frame() -> None:
    minimap = Minimap()
    built, _ = readers(Finder((611.5, 340)), minimap=minimap)
    older, frame = screen(at=AT - 0.1), screen()

    read = built.read(frame, older)

    assert minimap.frames == [older]
    assert read.minimap_at == AT - 0.1
    assert read.frame is frame


def test_a_frame_with_no_map_reads_nothing() -> None:
    r = tool.row(tool.no_map(screen(), "x.png"))

    assert r["map_id"] == ""
    assert {r[f"{read}_status"] for read in tool.READS} == {tool.SKIPPED}
    assert r["position_detail"] == "no map"


def rows(*cases: tuple[str, str, str, str]) -> list[dict[str, str]]:
    """Rows of map 1 from `(frame_ok, minimap, camera, position source or
    status)`, 0.1 s apart."""
    out: list[dict[str, str]] = []
    for i, (ok, minimap, camera, position) in enumerate(cases):
        r = dict.fromkeys(tool.FIELDS, "")
        source = position if position in ("fused", "coarse") else ""
        r.update(
            map_id="1",
            frame_ok=ok,
            captured_at=f"{i / 10:.3f}",
            age_ms="40.0",
            minimap_status=minimap,
            camera_status=camera,
            characters_status="read" if camera == "read" else tool.SKIPPED,
            position_status="read" if source else position,
            position_source=source,
            own_elsewhere="0",
            still="0",
        )
        out.append(r)
    return out


def test_rates_count_each_read_on_the_frames_it_was_asked_on() -> None:
    rates = tool.map_rates(
        rows(
            ("1", "read", "read", "fused"),
            ("1", "read", "unsure", "coarse"),
            ("1", "covered", tool.SKIPPED, "unsure"),
            ("0", "unsure", tool.SKIPPED, "unsure"),
            ("1", "unsure", tool.SKIPPED, "unsure"),
            ("1", "read", "read", "fused"),
        )
    )["1"]

    assert (rate := rates).frames == 6
    assert rate.counted == 5
    assert rate.asked == {"minimap": 5, "camera": 3, "characters": 2, "position": 5}
    assert dict(rate.not_read["minimap"]) == {"covered": 1, "unsure": 1}
    assert dict(rate.not_read["camera"]) == {"unsure": 1}
    assert dict(rate.not_read["position"]) == {"unsure": 2}
    assert dict(rate.sources) == {"fused": 2, "coarse": 1}
    assert rate.longest_unsure == (2, pytest.approx(0.2))
    assert len(rate.ages) == 5


def test_spreads_are_taken_on_still_frames_only() -> None:
    table = rows(*[("1", "read", "read", "fused")] * 4)
    for r, (x, still) in zip(
        table, ((600, "1"), (602, "1"), (601, "1"), (700, "0")), strict=True
    ):
        r.update(
            still=still,
            minimap_x="608",
            minimap_y="344",
            play_x=f"{x}.0",
            play_y="340.0",
            position_x=f"{x}.0",
            position_y="340.0",
        )

    spread = tool.spreads(table)["1"]

    assert spread["minimap"].range == (0.0, 0.0)
    assert spread["play area"].samples == 3
    assert spread["play area"].range == (2.0, 0.0)
    assert spread["fused"].std[0] == pytest.approx(0.8165, abs=1e-3)
    text = tool.summary(table, {"1": "Victoria Road: Ellinia"})
    assert "map 1 Victoria Road: Ellinia: 4 frames" in text
    assert "still, play area 3 frames" in text


class Check:
    def frame_usable(self, frame: Frame) -> Reading[None] | None:
        return None if frame.ok else Reading.unsure(frame.captured_at, frame.reason)


def test_a_saved_frame_is_laid_out_for_the_capture_tool_with_its_map(
    tmp_path: Path,
) -> None:
    built, _ = readers(Finder((611.5, 340)))
    read = built.read(screen())

    file = tool.save(read, tmp_path, Check())

    assert file is not None
    assert cv2.imread(str(tmp_path / file)) is not None
    (entry,) = json.loads((tmp_path / "frames.json").read_text())["frames"]
    assert entry["file"] == file
    assert entry["client_size"] == [1366, 768]
    assert entry["expect"] == {"map_id": {"status": "read", "value": 10002000}}
    assert "fused (611.5, 340.0)" in entry["notes"]
    assert tool.save(built.read(screen(ok=False)), tmp_path, Check()) is None


def test_replay_reads_map_by_map_in_the_manifests_order(tmp_path: Path) -> None:
    for name in ("a.png", "b.png", "c.png", "d.png"):
        (tmp_path / name).write_bytes(b"")
    manifest = {
        "frames": [
            {"file": "c.png", "expect": {"map_id": {"status": "read", "value": 2}}},
            {"file": "a.png", "expect": {}},
            {"file": "gone.png", "expect": {"map_id": {"status": "read", "value": 1}}},
            {"file": "d.png", "expect": {"map_id": {"status": "read", "value": 1}}},
            {"file": "b.png", "expect": {"map_id": {"status": "read", "value": 2}}},
        ]
    }
    (tmp_path / "frames.json").write_text(json.dumps(manifest))

    assert tool.replay_order(tmp_path, None, None) == [
        (2, ["c.png", "b.png"]),
        (1, ["d.png"]),
        (None, ["a.png"]),
    ]
    assert tool.replay_order(tmp_path, None, 7) == [
        (7, ["c.png", "a.png", "d.png", "b.png"])
    ]
    (tmp_path / "frames.json").unlink()
    assert tool.replay_order(tmp_path, None, None) == [
        (None, ["a.png", "b.png", "c.png", "d.png"])
    ]


def test_the_minimap_lag_picks_the_newest_frame_that_old() -> None:
    history = [screen(at=t) for t in (10.0, 10.5, 11.0, 11.5, 12.0)]

    assert tool.lagged(history, 0) is history[-1]
    assert tool.lagged(history, 1.0) is history[2]
    assert tool.lagged(history, 50) is history[0]


def test_the_csv_has_one_row_per_frame_and_a_summary_beside_it(tmp_path: Path) -> None:
    built, _ = readers(Finder((611.5, 340)))
    output = tool.Output(tmp_path, AT)
    for _ in range(3):
        output.write(built.read(screen()))

    text = output.close()

    with (tmp_path / "readings.csv").open(newline="") as f:
        written = list(csv.DictReader(f))
    assert [r["position_source"] for r in written] == ["fused"] * 3
    assert (tmp_path / "summary.txt").read_text().strip() == text
    assert "fused 3/3 (100%)" in text


def test_it_loads_nothing_that_sends_input() -> None:
    """Sends no keys, ever: importing the tool loads no input module."""
    code = (
        "import sys, toolkit.position_check\n"
        "print('\\n'.join(m for m in sys.modules if m.startswith("
        "('botting.controller', 'pydirectinput', 'pyautogui'))))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert loaded == []
