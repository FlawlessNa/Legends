"""
The `Locator` and the frame check, on synthetic frames: a plain background
with sprites the test pastes, and occluders it paints over them.
"""

import numpy as np
import pytest

from botting.screen import Frame, Reading, Status
from game_data.sprites import Sprite
from maple.screen.locator import (
    UI_NOT_FOUND,
    FrameCheck,
    Locator,
    Part,
    located_status,
    unreadable,
)
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

RNG = np.random.default_rng(307)


def sprite(path: str, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> Sprite:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, origin)


# An element drawn at a point: its anchor with its origin there, and two parts
# placed from it by vectors, the way the client places them.
ANCHOR = sprite("UI/Thing.img/backgrnd", 12, 8, origin=(2, 3))
LEFT = sprite("UI/Thing.img/left", 6, 5, origin=(1, 1))
RIGHT = sprite("UI/Thing.img/right", 7, 4)
LEFT_AT = (-10, 20)
RIGHT_AT = (15, 18)


def locator() -> Locator:
    return Locator(Part(ANCHOR), (Part(LEFT, LEFT_AT), Part(RIGHT, RIGHT_AT)))


def blank(w: int = 200, h: int = 150) -> np.ndarray:
    return np.full((h, w, 3), 40, dtype=np.uint8)


def paste(pixels: np.ndarray, s: Sprite, x: int, y: int) -> None:
    h, w = s.rgba.shape[:2]
    pixels[y : y + h, x : x + w] = s.rgba[:, :, 2::-1]


def element(point: tuple[int, int], w: int = 200, h: int = 150) -> np.ndarray:
    pixels = blank(w, h)
    px, py = point
    paste(pixels, ANCHOR, px - 2, py - 3)
    paste(pixels, LEFT, px + LEFT_AT[0] - 1, py + LEFT_AT[1] - 1)
    paste(pixels, RIGHT, px + RIGHT_AT[0], py + RIGHT_AT[1])
    return pixels


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 12.5, True, ok, reason)


def test_a_whole_element_is_found_at_its_point() -> None:
    located = locator().locate(frame(element((60, 40))))

    assert located is not None
    assert located.point == (60, 40)
    assert located.complete
    assert (located.anchor.x, located.anchor.y) == (58, 37)
    assert [(p.path, p.x, p.y, p.matched) for p in located.parts] == [
        (LEFT.path, 49, 59, True),
        (RIGHT.path, 75, 58, True),
    ]
    assert located.position(LEFT_AT) == (50, 60)
    assert located_status(located) is Status.READ
    assert unreadable(located, frame(blank())) is None


def test_the_anchor_is_rechecked_not_searched_on_the_next_frame() -> None:
    finder = locator()
    finder.locate(frame(element((60, 40))))
    located = finder.locate(frame(element((60, 40))))

    assert finder.searches == 1
    assert located is not None
    assert located.complete


def test_a_moved_element_is_searched_again() -> None:
    finder = locator()
    finder.locate(frame(element((60, 40))))
    located = finder.locate(frame(element((90, 50))))

    assert finder.searches == 2
    assert located is not None
    assert located.point == (90, 50)


def test_one_search_after_a_size_change_then_rechecks() -> None:
    finder = locator()
    finder.locate(frame(element((60, 40))))
    # The same place, but the client was resized: the remembered position isn't trusted.
    first = finder.locate(frame(element((60, 40), w=240, h=180)))
    second = finder.locate(frame(element((60, 40), w=240, h=180)))

    assert finder.searches == 2
    assert first is not None
    assert first.complete
    assert second is not None
    assert second.complete


def test_a_covered_anchor_is_found_through_a_fixed_part_and_covered() -> None:
    pixels = element((60, 40))
    pixels[35:47, 55:72] = 255  # an occluder over the whole anchor
    finder = locator()

    located = finder.locate(frame(pixels))

    assert located is not None
    assert located.point == (60, 40)
    assert not located.anchor.matched
    assert all(p.matched for p in located.parts)
    assert located_status(located) is Status.COVERED
    reading = unreadable(located, frame(pixels))
    assert reading is not None
    assert reading.status is Status.COVERED
    assert reading.value is None
    assert ANCHOR.path in reading.detail


def test_a_covered_part_beside_a_found_anchor_is_covered() -> None:
    pixels = element((60, 40))
    pixels[58:63, 75:78] = 0  # part of the right-hand part
    located = locator().locate(frame(pixels))

    assert located is not None
    assert located.anchor.matched
    assert located_status(located) is Status.COVERED
    reading = unreadable(located, frame(pixels))
    assert reading is not None
    assert reading.detail.endswith(RIGHT.path)


def test_nothing_found_is_absent() -> None:
    located = locator().locate(frame(blank()))

    assert located is None
    assert located_status(located) is Status.ABSENT
    reading = unreadable(located, frame(blank()))
    assert reading is not None
    assert reading.status is Status.ABSENT
    assert reading.frame_time == 12.5


def test_an_element_partly_off_the_frame_is_covered_not_an_error() -> None:
    pixels = element((60, 40))
    finder = locator()
    finder.locate(frame(pixels))
    # The same size, but the anchor is now at the left edge and the left part off it.
    located = finder.locate(frame(element((4, 40))))

    assert located is not None
    assert located.anchor.matched
    assert located_status(located) is Status.COVERED


GAUGE = sprite(GAUGE_LABEL, 9, 6)


@pytest.fixture
def check() -> FrameCheck:
    return FrameCheck(ReaderSprites("b", {GAUGE_LABEL: GAUGE}))


def with_gauge() -> np.ndarray:
    pixels = blank()
    paste(pixels, GAUGE, 30, 130)
    return pixels


def test_a_frame_with_the_status_bar_anchor_is_usable(check: FrameCheck) -> None:
    assert check.frame_usable(frame(with_gauge())) is None


def test_a_frame_that_isnt_ok_is_unsure_with_its_reason(check: FrameCheck) -> None:
    reading = check.frame_usable(
        frame(with_gauge(), ok=False, reason="window not in front")
    )

    assert reading is not None
    assert reading.status is Status.UNSURE
    assert reading.detail == "frame not usable: window not in front"
    assert check.locator.searches == 0


def test_a_frame_without_the_anchor_at_1_to_1_is_unsure(check: FrameCheck) -> None:
    # The UI drawn at another scale: the anchor is there, but not pixel for pixel.
    pixels = blank()
    scaled = np.repeat(np.repeat(GAUGE.rgba[:, :, 2::-1], 2, axis=0), 2, axis=1)
    pixels[100:112, 30:48] = scaled

    reading = check.frame_usable(frame(pixels))

    assert reading is not None
    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


def test_readers_sharing_a_frame_check_it_once(check: FrameCheck) -> None:
    shared = frame(with_gauge())
    check.frame_usable(shared)
    check.frame_usable(shared)
    check.frame_usable(frame(with_gauge()))

    assert check.locator.searches == 1


def test_an_unusable_frame_reading_is_any_readers_reading(check: FrameCheck) -> None:
    def read_something(f: Frame) -> Reading[int]:
        if (unusable := check.frame_usable(f)) is not None:
            return unusable
        return Reading.read(3, f.captured_at)

    assert read_something(frame(blank())).status is Status.UNSURE
    assert read_something(frame(with_gauge())).value == 3
