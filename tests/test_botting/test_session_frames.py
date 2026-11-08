"""
`python -m botting.session frame`, the checkpoint mapping it rests on, the
recorder's `recording.*` records, and the `[TEST]` recording section.

The video is a tiny one generated into `tmp_path`: frame `k` is a flat grey of
value `10 * k`, so the frame a command cut is read back off its pixels. MJPG is
lossy, so pixels are compared within a tolerance.
"""

import asyncio
import configparser
import datetime
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from botting.screen_recorder import recorder as recorder_module
from botting.screen_recorder.recorder import Recorder, section_config
from botting.session.cli import main
from botting.session.frames import FrameError, frame_index_at, parse_box

ZONE = datetime.timezone(datetime.timedelta(hours=-5))
START = datetime.datetime(2026, 11, 8, 10, 0, 0, tzinfo=ZONE)
WIDTH, HEIGHT, FRAMES = 64, 48, 20


def write_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter.fourcc(*"MJPG"), 10.0, (WIDTH, HEIGHT)
    )
    for k in range(FRAMES):
        writer.write(np.full((HEIGHT, WIDTH, 3), 10 * k, dtype=np.uint8))
    writer.release()
    assert path.is_file()


def write_session(
    directory: Path, records: list[tuple[float, str, dict[str, Any]]]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "timestamp": (START + datetime.timedelta(seconds=t)).isoformat(),
                "correlation_id": None,
                "logger_name": "test",
                "event_type": event_type,
                "payload": payload,
            }
        )
        for t, event_type, payload in records
    ]
    (directory / "telemetry.jsonl").write_text("\n".join(lines) + "\n")
    return directory


def recorded(tmp_path: Path, checkpoints: list[tuple[float, int]]) -> Path:
    """A Session whose recorder started 0.5 s before `session.started`."""
    video = tmp_path / "rec.avi"
    write_video(video)
    return write_session(
        tmp_path / "session",
        [
            (-0.5, "recording.started", {"path": str(video), "fps": 30.0}),
            (0.0, "session.started", {"bots": [], "debug": False}),
            *[(t, "recording.checkpoint", {"frame_index": i}) for t, i in checkpoints],
        ],
    )


#: Frames 0, 8 and 16 at -0.5 s, 0.5 s and 2.5 s: the recorder slowed down in
#: the second segment (4 frames per second), so frame / rate would be wrong.
DRIFTING = [(-0.5, 0), (0.5, 8), (2.5, 16)]


@pytest.mark.parametrize(
    ("t", "index"),
    [
        (-0.5, 0),  # on a checkpoint
        (0.5, 8),
        (0.0, 4),  # halfway through the first segment, before session.started
        (1.5, 12),  # halfway through the slow segment
        (2.5, 16),
        (-1.5, 0),  # before the first checkpoint, clamped at the first frame
        (3.5, 20),  # after the last: the last segment's rate goes on
    ],
)
def test_a_time_maps_to_a_frame_between_the_checkpoints_either_side(
    t: float, index: int
) -> None:
    assert frame_index_at(DRIFTING, t) == index


def test_drift_between_checkpoints_does_not_accumulate() -> None:
    # A slow stretch early on must not shift a time long after it.
    checkpoints = [(0.0, 0), (1.0, 8), (4.0, 16), (5.0, 24), (6.0, 32)]
    assert frame_index_at(checkpoints, 5.5) == 28
    assert frame_index_at(checkpoints, 2.5) == 12


def test_fewer_than_two_checkpoints_fix_no_rate() -> None:
    with pytest.raises(FrameError, match="at least 2"):
        frame_index_at([(0.0, 0)], 1.0)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def read_png(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    assert image is not None
    return image


def test_frame_writes_the_png_of_the_frame_the_time_maps_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = recorded(tmp_path, DRIFTING)

    code, out, _ = run(capsys, "frame", str(session), "--at", "+00:01.5", "--json")

    assert code == 0
    result = json.loads(out)
    assert result["frame_index"] == 12
    png = Path(result["path"])
    assert png.parent == session / "frames"
    image = read_png(png)
    assert image.shape == (HEIGHT, WIDTH, 3)
    assert abs(int(image.mean()) - 120) <= 6  # frame 12 is grey 120


def test_frame_box_is_in_screen_pixels_and_scale_resizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = recorded(tmp_path, DRIFTING)

    code, out, _ = run(
        capsys,
        *["frame", str(session), "--at", "0.5", "--box", "8,4,40,20"],
        *["--scale", "2", "--json"],
    )

    assert code == 0
    assert read_png(Path(json.loads(out)["path"])).shape == (32, 64, 3)


def test_frame_box_past_the_frame_is_clipped_and_one_wholly_outside_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = recorded(tmp_path, DRIFTING)

    code, out, _ = run(
        capsys, "frame", str(session), "--at", "0.5", "--box", "32,24,500,500", "--json"
    )
    assert code == 0
    assert read_png(Path(json.loads(out)["path"])).shape == (24, 32, 3)

    code, _, err = run(
        capsys, "frame", str(session), "--at", "0.5", "--box", "100,100,200,200"
    )
    assert code == 1
    assert "outside" in err


def test_frame_without_a_recording_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = write_session(
        tmp_path / "s", [(0.0, "session.started", {"bots": [], "debug": True})]
    )

    code, out, err = run(capsys, "frame", str(session), "--at", "1")

    assert code == 1
    assert out == ""
    assert "no recording" in err
    assert "debug" in err
    assert not (session / "frames").exists()


def test_frame_says_so_when_the_video_was_pruned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = recorded(tmp_path, DRIFTING)
    (tmp_path / "rec.avi").unlink()

    code, _, err = run(capsys, "frame", str(session), "--at", "1")

    assert code == 1
    assert "no longer exists" in err


def test_frame_past_the_end_of_the_video_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = recorded(tmp_path, DRIFTING)

    code, _, err = run(capsys, "frame", str(session), "--at", "+10:00")

    assert code == 1
    assert "past the end" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["frame"],
        ["frame", "--at", "1", "--box", "1,2,3"],
        ["frame", "--at", "1", "--box", "5,5,1,9"],
        ["frame", "--at", "1", "--scale", "0"],
    ],
)
def test_frame_refuses_bad_arguments_with_exit_code_2(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert stop.value.code == 2
    capsys.readouterr()


def test_parse_box() -> None:
    assert parse_box("1,2,30,40").right == 30


# --- The recorder -----------------------------------------------------------------


def ini(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parser


RECORDINGS = """
[DEFAULT]
Four CC = XVID
FPS = 8
[TEST]
Four CC = MJPG
"""


def test_test_section_overrides_default_and_inherits_the_rest() -> None:
    config = section_config(ini(RECORDINGS), "TEST")

    assert config["four cc"] == "MJPG"
    assert config["fps"] == "8"


def test_default_section_is_unchanged() -> None:
    assert section_config(ini(RECORDINGS), "DEFAULT")["four cc"] == "XVID"


def test_a_missing_test_section_falls_back_to_default_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        config = section_config(ini("[DEFAULT]\nFour CC = XVID\n"), "TEST")

    assert config["four cc"] == "XVID"
    assert "[TEST]" in caplog.text


class _Writer:
    def __init__(self) -> None:
        self.frames = 0

    def write(self, _: object) -> None:
        self.frames += 1

    def release(self) -> None:
        pass


class _Cleanup:
    def perform_cleanup(self) -> None:
        pass


def test_recorder_emits_started_then_a_checkpoint_every_config_fps_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[tuple[str, dict[str, Any]]] = []
    writer = _Writer()

    def fake_emit(
        _cid: object, event_type: str, payload: Mapping[str, object], **_: object
    ) -> None:
        emitted.append((event_type, dict(payload)))
        if writer.frames >= 9:  # nine frames written: stop the loop
            raise asyncio.CancelledError

    monkeypatch.setattr(recorder_module, "emit_event", fake_emit)
    monkeypatch.setattr(recorder_module, "take_screenshot", lambda: None)
    rec = Recorder.__new__(Recorder)
    rec.config = {"fps": "4", "multiplier": "3"}
    rec.out_path = "x.avi"
    rec.output = writer  # pyright: ignore[reportAttributeAccessIssue]
    rec.output_manager = _Cleanup()  # pyright: ignore[reportAttributeAccessIssue]

    asyncio.run(rec.start())

    assert emitted[0] == ("recording.started", {"path": "x.avi", "fps": 12.0})
    # Frames 0, 4 and 8 are checkpoints; the third ends the loop (9 frames).
    assert emitted[1:] == [
        ("recording.checkpoint", {"frame_index": 0}),
        ("recording.checkpoint", {"frame_index": 4}),
        ("recording.checkpoint", {"frame_index": 8}),
    ]
