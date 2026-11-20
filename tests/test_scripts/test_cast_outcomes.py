"""
`toolkit/cast_outcomes.py` on a synthetic Session: a JSONL log and a video built
here, with stand-in digit sprites over a plain background (#640). No client
files: the real digits are the catalogue's, which this machine's test run
doesn't have.
"""

import datetime
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from botting.session.reading import load_session
from game_data.catalogue import Catalogue, build_catalogue
from game_data.extraction import extract
from game_data.render import Images
from game_data.scenes.occluders import Sprites, damage
from tests.test_game_data.test_scenes import write_scenes_client
from toolkit import cast_outcomes as co

SCREEN = (400, 300)  # width, height
FEET = (150.0, 200.0)
ORIGIN = (20, 10)
BACKGROUND = 90
FPS_PER_SECOND = 8  # frames per second of Session time
START = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=datetime.UTC)


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scenes test's fixture client, extracted: no `data/` needed."""
    base = tmp_path_factory.mktemp("cast_outcomes")
    root = base / "store"
    extract(write_scenes_client(base / "Data"), root, catalogue=build_catalogue)
    return root


@pytest.fixture(scope="module")
def templates(store: Path) -> list[co.Template]:
    return co.catalogue_templates(1.0, store)


def number_over(store: Path, head: tuple[int, int], seed: int = 0) -> np.ndarray:
    """
    A plain screen with a real damage number above screen pixel `head`, composed
    as the scenes do (`occluders.damage`: the digits overlap by `DIGIT_OVERLAP`).
    """
    width, height = SCREEN
    frame = np.full((height, width, 3), BACKGROUND, np.uint8)
    with Catalogue.latest(store) as cat:
        sprites = Sprites.read(cat)
        overlays = damage(
            sprites,
            Images(cat.store.images),
            head[0],
            head[1],
            np.random.default_rng(seed),
        )
    for overlay in overlays:
        rgba = overlay.pixels
        h, w = rgba.shape[:2]
        region = frame[overlay.top : overlay.top + h, overlay.left : overlay.left + w]
        opaque = rgba[..., 3] > 127
        region[opaque] = rgba[..., 2::-1][opaque]
    return frame


def blank() -> np.ndarray:
    width, height = SCREEN
    return np.full((height, width, 3), BACKGROUND, np.uint8)


def mob(left: int, right: int) -> dict[str, int]:
    """A mob box from the feet, 40 px tall."""
    return {"left": left, "top": -40, "right": right, "bottom": 0}


def anchor() -> dict[str, Any]:
    return {
        "feet_x": FEET[0],
        "feet_y": FEET[1],
        "client_left": ORIGIN[0],
        "client_top": ORIGIN[1],
    }


def screen_of(offset_x: int, offset_y: int) -> tuple[int, int]:
    return (
        round(FEET[0]) + ORIGIN[0] + offset_x,
        round(FEET[1]) + ORIGIN[1] + offset_y,
    )


def line(t: float, event: str, payload: dict[str, Any]) -> str:
    stamp = (START + datetime.timedelta(seconds=t)).isoformat()
    return json.dumps(
        {
            "timestamp": stamp,
            "correlation_id": None,
            "logger_name": "test",
            "event_type": event,
            "payload": payload,
        }
    )


def test_a_number_over_a_counted_mob_is_a_hit_and_none_is_a_miss(
    store: Path, templates: list[co.Template]
) -> None:
    near, far = mob(-70, -50), mob(40, 60)
    record = _record(1.0, "combat.mobs_hit", mobs=[near, far])
    # A number 10 px above the near mob's head, which is its top middle.
    head = screen_of(-60, -40 - 10)
    frames = [blank(), number_over(store, head)]

    cast = co.judge(record, frames, templates, co.TOLERANCE)

    assert (cast.mobs, cast.hit, cast.missed) == (2, 1, False)


def test_every_number_length_over_a_mob_is_found(
    store: Path, templates: list[co.Template]
) -> None:
    """Numbers of 1 to 6 digits, overlapping by `DIGIT_OVERLAP` as drawn."""
    record = _record(1.0, "combat.mobs_hit", mobs=[mob(-70, -50)])
    head = screen_of(-60, -40 - 5)

    hits = [
        co.judge(record, [number_over(store, head, seed)], templates, co.TOLERANCE).hit
        for seed in range(12)
    ]

    assert hits == [1] * 12


def test_a_cast_with_no_number_over_any_mob_is_a_miss(
    store: Path, templates: list[co.Template]
) -> None:
    record = _record(1.0, "combat.mobs_hit", mobs=[mob(-70, -50)])
    # A number, but over where no counted mob is.
    frames = [number_over(store, (350, 270))]

    cast = co.judge(record, frames, templates, co.TOLERANCE)

    assert (cast.mobs, cast.hit, cast.missed) == (1, 0, True)


def test_only_the_sets_that_hit_a_mob_are_templates(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert len(co.catalogue_templates(1.0, store)) == 20
    monkeypatch.setattr(co, "DAMAGE_SETS", ("NoViolet",))

    with pytest.raises(co.ReportError, match="no damage digit"):
        co.catalogue_templates(1.0, store)


def test_scale_grows_the_templates_and_the_search_region(store: Path) -> None:
    one, two = co.catalogue_templates(1.0, store), co.catalogue_templates(2.0, store)
    assert two[0].pixels.shape[0] == 2 * one[0].pixels.shape[0]
    payload = {**anchor(), "mobs": [mob(-70, -50)]}
    [first] = co.mob_regions(payload)
    [second] = co.mob_regions(payload, 2.0)
    assert second[0] < first[0]
    assert second[1] < first[1]
    assert second[2] > first[2]


def test_a_session_from_before_the_anchor_fields_is_refused() -> None:
    record = _record(1.0, "combat.mobs_hit", mobs=[mob(0, 10)])
    bare = co.Record(
        record.line,
        record.timestamp,
        None,
        "t",
        "combat.mobs_hit",
        {"mob_count": 1, "attack": "x", "direction": None, "mobs": [mob(0, 10)]},
    )

    with pytest.raises(co.ReportError, match="before #640"):
        co.check_anchored([bare])


def test_the_report_over_a_video_gives_hits_misses_and_skipped_mobs(
    tmp_path: Path, store: Path, templates: list[co.Template]
) -> None:
    video = tmp_path / "rec.avi"
    # 24 frames, 8 a second. A number over the mob from second 1.0 to 1.5 only.
    shown = number_over(store, screen_of(-60, -40 - 10))
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*"MJPG"), 8, SCREEN)
    for index in range(24):
        writer.write(shown if 8 <= index <= 12 else blank())
    writer.release()

    events = [
        line(0.0, "session.started", {}),
        line(0.0, "recording.started", {"path": str(video), "fps": 8}),
        line(0.0, "recording.checkpoint", {"frame_index": 0}),
        line(1.0, "recording.checkpoint", {"frame_index": 8}),
        line(2.0, "recording.checkpoint", {"frame_index": 16}),
        line(3.0, "recording.checkpoint", {"frame_index": 24}),
        line(
            1.0,
            "combat.mobs_hit",
            {
                "mob_count": 1,
                "direction": "left",
                "attack": "Power Strike",
                "mobs": [mob(-70, -50)],
                **anchor(),
            },
        ),
        line(
            2.0,
            "combat.mobs_hit",
            {
                "mob_count": 1,
                "direction": "left",
                "attack": "Power Strike",
                "mobs": [mob(-70, -50)],
                **anchor(),
            },
        ),
        line(
            2.5,
            "combat.partial_reach",
            {"attack": "Slash Blast", "mobs": [mob(-100, -80)], **anchor()},
        ),
    ]
    path = tmp_path / "telemetry.jsonl"
    path.write_text("\n".join(events), encoding="utf-8")

    casts, partials = co.report(
        load_session(path), video, templates, cast_time=0.75, tolerance=0.2
    )

    assert [(c.attack, c.mobs, c.hit) for c in casts] == [
        ("Power Strike", 1, 1),
        ("Power Strike", 1, 0),
    ]
    assert [(p.attack, p.offsets) for p in partials] == [
        ("Slash Blast", ((-100, -40, -80, 0),))
    ]
    text = "\n".join(co.lines(casts, partials))
    assert "total: 2 casts, 1 hit, 1 missed" in text
    assert "partial reach: 1 events" in text


def _record(t: float, event: str, mobs: list[dict[str, int]]) -> co.Record:
    return co.Record(
        1,
        START,
        None,
        "t",
        event,
        {
            "mob_count": len(mobs),
            "direction": "left",
            "attack": "Power Strike",
            "mobs": mobs,
            **anchor(),
        },
        t,
    )
