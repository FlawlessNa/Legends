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
from toolkit import cast_outcomes as co

SCREEN = (400, 300)  # width, height
FEET = (150.0, 200.0)
ORIGIN = (20, 10)
BACKGROUND = 90
FPS_PER_SECOND = 8  # frames per second of Session time
START = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=datetime.UTC)


def sprites() -> list[np.ndarray]:
    """Ten 8x12 RGBA stand-in digits, each its own noise, fully opaque."""
    rng = np.random.default_rng(1)
    digits = []
    for _ in range(10):
        rgba = rng.integers(0, 256, (12, 8, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        digits.append(rgba)
    return digits


DIGITS = sprites()
TEMPLATES = [co.template(d) for d in DIGITS]


def screen_with_number(at: tuple[int, int] | None) -> np.ndarray:
    """A plain screen, with digit 3 drawn with its top left at `at`."""
    width, height = SCREEN
    frame = np.full((height, width, 3), BACKGROUND, np.uint8)
    if at is not None:
        x, y = at
        digit = cv2.cvtColor(DIGITS[3], cv2.COLOR_RGBA2BGR)
        frame[y : y + 12, x : x + 8] = digit
    return frame


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


def test_a_number_over_a_counted_mob_is_a_hit_and_none_is_a_miss() -> None:
    near, far = mob(-70, -50), mob(40, 60)
    record = _record(1.0, "combat.mobs_hit", mobs=[near, far])
    # A number 10 px above the near mob's head, centred on it.
    x, y = screen_of(-60 - 4, -40 - 10 - 12)
    frames = [screen_with_number(None), screen_with_number((x, y))]

    cast = co.judge(record, frames, TEMPLATES, co.TOLERANCE)

    assert (cast.mobs, cast.hit, cast.missed) == (2, 1, False)


def test_a_cast_with_no_number_over_any_mob_is_a_miss() -> None:
    record = _record(1.0, "combat.mobs_hit", mobs=[mob(-70, -50)])
    # A number, but over where no counted mob is.
    frames = [screen_with_number((350, 250))]

    cast = co.judge(record, frames, TEMPLATES, co.TOLERANCE)

    assert (cast.mobs, cast.hit, cast.missed) == (1, 0, True)


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
    tmp_path: Path,
) -> None:
    video = tmp_path / "rec.avi"
    # 24 frames, 8 a second. A number over the mob from second 1.0 to 1.5 only.
    hit_at = screen_of(-60 - 4, -40 - 10 - 12)
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*"MJPG"), 8, SCREEN)
    for index in range(24):
        shown = hit_at if 8 <= index <= 12 else None
        writer.write(screen_with_number(shown))
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
        load_session(path), video, TEMPLATES, cast_time=0.75, tolerance=0.2
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
