"""
`toolkit/position_check.py` replaying the real frame set: its CSV says, frame
by frame, what the production readers say when called directly, and its rates
are theirs (#393; epic #302 Part 2, acceptance criterion 10). Run with
`pytest -m frames`; it needs the game data store.

The direct calls read the frames as the fusion frame test does
(`test_position_fusion_frames`): map by map, in the set's order within each
map, one `NameTagFinder` for the whole set, and each map's own minimap reader,
camera reader and fusion. The camera reader and the finder are also called
directly, with the seed fusion gave the camera, on the frames fusion asked them
on: a frame always reads the same, so each says what it said to fusion.
"""

import csv
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from botting.screen import Frame, Reading, Status
from game_data.config import CONFIG, STORE
from maple.model.world import WorldMap
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapView
from maple.screen.position import (
    Camera,
    CameraReader,
    CharacterSighting,
    Fusion,
    NameTagFinder,
    PositionFusion,
)
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameEntry, FrameSet
from toolkit import position_check as tool

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Direct:
    """One frame, as the production readers read it called directly."""

    entry: FrameEntry
    minimap: Reading[MinimapView] | None
    camera: Reading[Camera] | None
    characters: Reading[list[CharacterSighting]] | None
    fusion: Fusion | None


def _order(frames: FrameSet) -> list[tuple[int | None, list[FrameEntry]]]:
    out: dict[int | None, list[FrameEntry]] = {}
    for entry in frames.entries:
        map_id = entry.expect.get("map_id")
        key = map_id.value if map_id and map_id.status is Status.READ else None
        out.setdefault(key, []).append(entry)
    labelled: list[tuple[int | None, list[FrameEntry]]] = [
        (m, e) for m, e in out.items() if m is not None
    ]
    return labelled + ([(None, out[None])] if None in out else [])


def _read_map(
    frames: FrameSet, map_id: int, entries: list[FrameEntry], finder: NameTagFinder
) -> Iterator[Direct]:
    profile = Profile(job="", game_map="", map_id=map_id)
    sprites = load_reader_sprites([FRAME_CHECK, MINIMAP], profile, STORE, config=CONFIG)
    frame_check = FrameCheck(sprites)
    minimap = MinimapReader(sprites, frame_check, map_id=map_id)
    world_map = WorldMap.load(map_id, root=STORE)
    assert world_map.minimap is not None
    camera = CameraReader(world_map, frame_check=frame_check)
    fusion = PositionFusion(world_map.minimap, lambda: camera, finder)
    seed: Camera | None = None
    for entry in entries:
        frame = Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)
        mm = minimap.read(frame)
        fused = fusion.read(frame, mm)
        asked = mm.value is not None and mm.value.self_position.value is not None
        cam = camera.read(frame, seed) if asked else None
        found = finder.find(frame) if cam and cam.value is not None else None
        if cam is not None and cam.value is not None:
            seed = cam.value
        yield Direct(entry, mm, cam, found, fused)


@pytest.fixture(scope="module")
def tool_rows(
    frames: FrameSet, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, str]]:
    """The tool's replay of the set, as written to its CSV."""
    folder = tmp_path_factory.mktemp("position_check")
    output = tool.Output(folder, 0.0)
    labels = REPO / "tests" / "frames" / f"{frames.tag}.json"
    finder = tool.make_finder(None)
    for read, _ in tool.replay(frames.directory, finder, labels=labels):
        output.write(read)
    output.close()
    with output.csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def direct(frames: FrameSet, tool_rows: list[dict[str, str]]) -> list[Direct]:
    """Read after the tool, so one map's readers are held at a time."""
    finder = NameTagFinder()
    out: list[Direct] = []
    for map_id, entries in _order(frames):
        if map_id is None:
            out.extend(Direct(e, None, None, None, None) for e in entries)
        else:
            out.extend(_read_map(frames, map_id, entries, finder))
    return out


def _f(value: float | None, digits: int = 1) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def _status(reading: Reading[Any] | None) -> str:
    return tool.SKIPPED if reading is None else reading.status.value


def _expected(d: Direct) -> dict[str, str]:
    """The columns the tool must have written for `d`, from the direct calls."""
    out = {"frame": d.entry.file, "minimap_status": tool.SKIPPED}
    if d.minimap is None or d.fusion is None:
        return out | {"position_status": tool.SKIPPED, "camera_status": tool.SKIPPED}
    view = d.minimap.value
    marker = None if view is None else view.self_position
    position = d.fusion.position
    value = position.value
    camera = None if d.camera is None else d.camera.value
    found = None if d.characters is None else d.characters.value
    out |= {
        "minimap_status": (marker or d.minimap).status.value,
        "marker_x": ""
        if marker is None or marker.value is None
        else str(marker.value[0]),
        "marker_y": ""
        if marker is None or marker.value is None
        else str(marker.value[1]),
        "minimap_x": "" if d.fusion.minimap is None else str(d.fusion.minimap[0]),
        "minimap_y": "" if d.fusion.minimap is None else str(d.fusion.minimap[1]),
        "camera_status": _status(d.camera),
        "camera_x": "" if camera is None else str(camera.x),
        "camera_y": "" if camera is None else str(camera.y),
        "camera_share": "" if camera is None else _f(camera.share, 3),
        "camera_sharpness": "" if camera is None else _f(camera.sharpness, 3),
        "play_area_width": "" if camera is None else str(camera.play_area[0]),
        "characters_status": _status(d.characters),
        "characters_found": "" if found is None else str(len(found)),
        "characters_own": "" if found is None else str(sum(s.own for s in found)),
        "position_status": position.status.value,
        "position_source": "" if value is None else value.source.value,
        "position_x": _f(None if value is None else value.x),
        "position_y": _f(None if value is None else value.y),
        "near": str(d.fusion.near),
        "by_tag": str(int(d.fusion.by_tag)),
        "own_elsewhere": str(int(d.fusion.own_elsewhere)),
        "sightings": ";".join(
            f"{x:.1f}:{y:.1f}" + (":own" if found and found[i].own else "")
            for i, (x, y) in enumerate(d.fusion.sightings)
        ),
    }
    return out


def test_one_row_per_frame_in_the_order_they_are_read(
    frames: FrameSet, tool_rows: list[dict[str, str]]
) -> None:
    expected = [e.file for _, entries in _order(frames) for e in entries]
    assert [r["frame"] for r in tool_rows] == expected
    assert len(tool_rows) == len(frames.entries)


def test_each_row_has_the_values_and_statuses_the_readers_give_directly(
    tool_rows: list[dict[str, str]], direct: list[Direct]
) -> None:
    wrong: list[str] = []
    for r, d in zip(tool_rows, direct, strict=True):
        label = d.entry.expect.get("map_id")
        map_id = str(label.value) if label and label.status is Status.READ else ""
        if r["map_id"] != map_id:
            wrong.append(f"{d.entry.file}: map {r['map_id']!r}, labelled {map_id!r}")
        for column, value in _expected(d).items():
            if r[column] != value:
                wrong.append(
                    f"{d.entry.file}: {column} {r[column]!r}, directly {value!r}"
                )
    assert not wrong, "\n".join(wrong[:40])


def test_its_rates_are_the_readers_rates(
    tool_rows: list[dict[str, str]], direct: list[Direct]
) -> None:
    """Every frame of the set is the client's (`ok`), so every frame counts."""
    rates = tool.map_rates(tool_rows)
    for map_id, entries in _order_from(direct).items():
        rate = rates[str(map_id)]
        positions = [d.fusion.position for d in entries if d.fusion is not None]
        minimap = Counter(
            _minimap_status(d)
            for d in entries
            if _minimap_status(d) != Status.READ.value
        )
        sources = Counter(
            p.value.source.value for p in positions if p.value is not None
        )
        assert rate.counted == len(entries)
        assert dict(rate.not_read["minimap"]) == dict(minimap), map_id
        assert sum(rate.not_read["position"].values()) == sum(
            p.status is not Status.READ for p in positions
        ), map_id
        assert dict(rate.sources) == dict(sources), map_id
        camera = Counter(
            d.camera.status.value
            for d in entries
            if d.camera is not None and d.camera.status is not Status.READ
        )
        assert dict(rate.not_read["camera"]) == dict(camera), map_id
    assert sum(r.sources["fused"] for r in rates.values()) >= 230


def _minimap_status(d: Direct) -> str:
    assert d.minimap is not None
    view = d.minimap.value
    return (d.minimap if view is None else view.self_position).status.value


def _order_from(direct: list[Direct]) -> dict[int, list[Direct]]:
    out: dict[int, list[Direct]] = {}
    for d in direct:
        label = d.entry.expect.get("map_id")
        if label and label.status is Status.READ:
            out.setdefault(label.value, []).append(d)
    return out
