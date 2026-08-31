"""
Tests for the in-house `group_rectangles`.

`cv2.groupRectangles` was removed in OpenCV 5, so `botting/utilities/rectangles.py`
reimplements it. The expectations in `group_rectangles_golden.json` were captured
from the real `cv2.groupRectangles` under OpenCV 4.10 -- they are the contract,
and they cannot be regenerated from the pinned OpenCV any more. Treat a failure
here as the port drifting, never as a stale expectation.
"""

import json
from pathlib import Path

import pytest

from botting.utilities import group_rectangles

GOLDEN = json.loads(
    (Path(__file__).parent / "group_rectangles_golden.json").read_text()
)


@pytest.mark.parametrize("case", GOLDEN, ids=range(len(GOLDEN)))
def test_matches_opencv4_output(case):
    """Every recorded OpenCV 4.10 result is reproduced exactly."""
    rects, weights = group_rectangles(
        case["rects"], case["group_threshold"], case["eps"]
    )
    assert [list(map(int, r)) for r in rects] == case["expected_rects"]
    assert [int(w) for w in weights] == case["expected_weights"]


def test_duplicate_append_idiom_survives_threshold_one():
    """
    `find_image` appends each match twice so a lone match clears
    `group_threshold=1`. If that stopped working, template matching would
    silently return nothing.
    """
    rects, weights = group_rectangles([[10, 20, 30, 40]] * 2, 1, 0.5)
    assert [list(map(int, r)) for r in rects] == [[10, 20, 30, 40]]
    assert list(weights) == [2]


def test_single_rectangle_is_dropped_below_threshold():
    rects, weights = group_rectangles([[10, 20, 30, 40]], 1, 0.5)
    assert len(rects) == 0
    assert len(weights) == 0


def test_zero_threshold_passes_input_through_with_unit_weights():
    """OpenCV returns the input untouched but still emits a weight per rect."""
    rects, weights = group_rectangles([[1, 2, 3, 4], [5, 6, 7, 8]], 0, 0.5)
    assert [list(map(int, r)) for r in rects] == [[1, 2, 3, 4], [5, 6, 7, 8]]
    assert list(weights) == [1, 1]


def test_empty_input():
    rects, weights = group_rectangles([], 1, 0.5)
    assert len(rects) == 0
    assert len(weights) == 0
