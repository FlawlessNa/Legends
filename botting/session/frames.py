"""
Cutting a frame from a Session's video, at a moment on the Session's clock.

The recorder is real-time and best-effort, so frame ``k`` is not at ``k / fps``:
it drifts under load, and the declared rate is ``FPS * Multiplier`` while the
capture rate is ``FPS``. The ``recording.checkpoint`` records say which frame
had been written at which moment on the telemetry clock, about once a second.
A time is mapped by interpolating between the two checkpoints either side of
it, so drift never accumulates past one segment. Before the first checkpoint or
after the last, the nearest segment's rate is extended.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2

from botting.telemetry_events import RECORDING_CHECKPOINT, RECORDING_STARTED

from .reading import Session

#: Where in a Session directory frames are written.
FRAMES_DIRNAME: Final = "frames"


class FrameError(Exception):
    """A frame cannot be cut; the message says why and is meant to be printed."""


@dataclass(frozen=True, slots=True)
class Box:
    """A region of the screen in pixels: ``left, top`` inclusive, ``right, bottom`` not."""

    left: int
    top: int
    right: int
    bottom: int


def parse_box(text: str) -> Box:
    """
    Read ``l,t,r,b``, in screen pixels.
    :raises ValueError: when it is not four integers with ``l < r`` and ``t < b``.
    """
    try:
        left, top, right, bottom = (int(part) for part in text.split(","))
    except ValueError:
        raise ValueError(f"{text!r} is not l,t,r,b (four integers)") from None
    if not (0 <= left < right and 0 <= top < bottom):
        raise ValueError(f"{text!r}: need 0 <= l < r and 0 <= t < b")
    return Box(left, top, right, bottom)


def frame_index_at(checkpoints: Sequence[tuple[float, int]], t: float) -> int:
    """
    The frame being written at time ``t``, from ``(time, frame_index)``
    checkpoints. Never below 0.
    :param checkpoints: At least two, in time order.
    :param t: Seconds on the Session's clock.
    :raises FrameError: with fewer than two checkpoints, which fix no rate.
    """
    if len(checkpoints) < 2:
        raise FrameError(
            f"the recording has {len(checkpoints)} recording.checkpoint records; "
            "at least 2 are needed to map a time to a frame"
        )
    times = [time for time, _ in checkpoints]
    # The segment holding t; the first or last one when t is outside them all.
    upper = min(max(bisect.bisect_right(times, t), 1), len(checkpoints) - 1)
    (t0, i0), (t1, i1) = checkpoints[upper - 1], checkpoints[upper]
    if t1 == t0:
        return max(i0, 0)
    return max(round(i0 + (t - t0) * (i1 - i0) / (t1 - t0)), 0)


def cut_frame(
    session: Session, t: float, box: Box | None, scale: float
) -> tuple[Path, int]:
    """
    Write the frame at ``t`` as a PNG into ``<Session dir>/frames/``.
    :param session: The Session whose video to read.
    :param t: Seconds on the Session's clock.
    :param box: A region in screen pixels, clipped to the frame; the whole frame
        when ``None``.
    :param scale: Resize factor applied after cropping.
    :return: The PNG's path, and the frame index it was cut at.
    :raises FrameError: with no recording, no video file, or no such frame.
    """
    video = _video_path(session)
    checkpoints = [
        (r.t, frame_index)
        for r in session.records
        if r.event_type == RECORDING_CHECKPOINT
        and isinstance(frame_index := r.payload.get("frame_index"), int)
    ]
    index = frame_index_at(checkpoints, t)
    capture = cv2.VideoCapture(str(video))
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not capture.isOpened() or total <= 0:
            raise FrameError(f"{video} cannot be read as a video")
        if index >= total:
            raise FrameError(
                f"frame {index} is past the end of {video} ({total} frames): "
                "the recording stopped before that time"
            )
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = capture.read()
    finally:
        capture.release()
    if not ok:
        raise FrameError(f"could not read frame {index} of {video}")
    if box is not None:
        height, width = image.shape[:2]
        image = image[
            box.top : min(box.bottom, height), box.left : min(box.right, width)
        ]
        if image.size == 0:
            raise FrameError(f"the box lies outside the {width}x{height} frame")
    if scale != 1.0:
        image = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
    out_dir = session.path.parent / FRAMES_DIRNAME
    out_dir.mkdir(exist_ok=True)
    name = f"frame_{index:06d}"
    if box is not None:
        name += f"_{box.left}-{box.top}-{box.right}-{box.bottom}"
    if scale != 1.0:
        name += f"_x{scale:g}"
    out = out_dir / f"{name}.png"
    if not cv2.imwrite(str(out), image):
        raise FrameError(f"could not write {out}")
    return out, index


def _video_path(session: Session) -> Path:
    started = session.first(RECORDING_STARTED)
    if started is None:
        debug = session.first("session.started")
        why = (
            "a debug Session has no recording"
            if debug is not None and debug.payload.get("debug")
            else "the recorder was off, or the Session ended before it started"
        )
        raise FrameError(f"no recording: there is no recording.started record ({why})")
    path = started.payload.get("path")
    if not isinstance(path, str):
        raise FrameError("recording.started has no path")
    video = Path(path)
    if not video.is_file():
        raise FrameError(
            f"the video {video} no longer exists (the recordings folder is pruned "
            "oldest-first)"
        )
    return video
