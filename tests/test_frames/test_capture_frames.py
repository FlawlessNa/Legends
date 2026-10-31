"""`capture_frames.py` keeps only trusted frames, and writes a stub per frame."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import cv2
import numpy as np
import pytest

from botting.screen import Frame
from tests import frame_set

SCRIPT = Path(__file__).resolve().parents[2] / "toolkit" / "capture_frames.py"


@pytest.fixture
def capture() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capture_frames", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame(ok: bool) -> Frame:
    return Frame(
        pixels=np.zeros((6, 8, 3), np.uint8),
        client_size=(8, 6),
        captured_at=0.0,
        fresh=True,
        ok=ok,
        reason="" if ok else "covered",
    )


def test_unusable_frames_are_not_kept(capture: ModuleType, tmp_path: Path) -> None:
    assert capture.save_frame(frame(ok=False), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_a_usable_frame_is_written_with_a_stub(
    capture: ModuleType, tmp_path: Path
) -> None:
    first = capture.save_frame(frame(ok=True), tmp_path)
    second = capture.save_frame(frame(ok=True), tmp_path)

    written = cv2.imread(str(tmp_path / first))
    assert written is not None
    assert written.shape == (6, 8, 3)
    stubs = json.loads((tmp_path / "frames.json").read_text(encoding="utf-8"))["frames"]
    assert [s["file"] for s in stubs] == [first, second]
    assert stubs[0] == {
        "file": first,
        "client_size": [8, 6],
        "notes": "",
        "expect": {},
    }


def test_a_stub_is_not_a_finished_file(capture: ModuleType, tmp_path: Path) -> None:
    capture.save_frame(frame(ok=True), tmp_path)
    raw = json.loads((tmp_path / "frames.json").read_text(encoding="utf-8"))

    with pytest.raises(frame_set.FrameSetError, match="stub"):
        frame_set.parse_entries(raw, "stub")
