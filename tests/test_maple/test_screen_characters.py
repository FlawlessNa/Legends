"""
`CharacterFinder` on drawn frames: `NameTagFinder` lists every name tag with
the feet over it and learns ours from where the minimap puts it, and
`YoloCharacterFinder` turns a stub model's boxes into feet. The real frames are
`test_screen_characters_frames.py`.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from botting.screen import Frame, Status
from maple.screen.position import (
    CharacterFinder,
    CharacterSighting,
    NameTagFinder,
    YoloCharacterFinder,
    tag_upscale,
)
from maple.screen.position.characters import TAG_TO_FEET, TAG_X_TO_FEET

OURS = "Mangoose"
THEIRS = "Rower"
BACKGROUND = (150, 170, 130)


def blank(size: tuple[int, int] = (1366, 768)) -> NDArray[np.uint8]:
    width, height = size
    image = np.empty((height, width, 3), np.uint8)
    image[:] = BACKGROUND
    return image


def draw_tag(image: NDArray[np.uint8], text: str, left: int, baseline: int) -> None:
    """A name tag as the client draws one at 1:1: pure white text on a dark
    box."""
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_PLAIN, 1.0, 1)
    cv2.rectangle(
        image,
        (left - 3, baseline - h - 3),
        (left + w + 3, baseline + 4),
        (40, 35, 30),
        -1,
    )
    cv2.putText(
        image,
        text,
        (left, baseline),
        cv2.FONT_HERSHEY_PLAIN,
        1.0,
        (255, 255, 255),
        1,
        cv2.LINE_8,
    )


def text_box(
    image: NDArray[np.uint8], left: int, right: int
) -> tuple[int, int, int, int]:
    """The white text's box between columns `left` and `right`."""
    ys, xs = np.nonzero(image[:, left:right].min(axis=2) == 255)
    return (
        int(xs.min()) + left,
        int(ys.min()),
        int(xs.max()) + left + 1,
        int(ys.max()) + 1,
    )


def feet_over(
    box: tuple[int, int, int, int], scale: float = 1.0
) -> tuple[float, float]:
    x0, y0, x1, _ = box
    return (x0 + x1 - 1) / 2 + TAG_X_TO_FEET * scale, y0 - TAG_TO_FEET * scale


def frame(image: NDArray[np.uint8], ok: bool = True) -> Frame:
    height, width = image.shape[:2]
    return Frame(image, (width, height), 12.5, True, ok, "" if ok else "moved")


def taught(
    finder: NameTagFinder, image: NDArray[np.uint8], near: tuple[float, float]
) -> list[bool]:
    return [finder.learn_own(frame(image), near) for _ in range(3)]


# ----------------------------------------------------------------------- tag scale


@pytest.mark.parametrize(
    ("size", "scale"),
    [
        ((800, 600), 1.0),
        ((1024, 768), 1.0),
        ((1280, 720), 1.0),
        ((1366, 768), 1.0),
        ((1920, 1080), 1080 / 768),
        ((1920, 1200), 1200 / 768),
        ((2560, 1440), 1440 / 768),
        ((1600, 900), None),
        ((1366, 1024), None),
    ],
)
def test_tag_scale_is_known_only_for_measured_sizes(
    size: tuple[int, int], scale: float | None
) -> None:
    assert tag_upscale(size) == scale


# ------------------------------------------------------------------------ name tags


def test_both_finders_are_character_finders() -> None:
    finders: list[CharacterFinder] = [
        NameTagFinder(),
        YoloCharacterFinder(StubModel([])),
    ]
    assert len(finders) == 2


def test_every_tag_is_listed_with_the_feet_over_it() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    draw_tag(image, THEIRS, 800, 500)
    reading = NameTagFinder().find(frame(image))
    assert reading.status is Status.READ
    assert reading.frame_time == 12.5
    assert reading.detail == "our tag not learned"
    assert reading.value is not None
    found = sorted(reading.value, key=lambda s: s.feet)
    assert [s.feet for s in found] == [
        feet_over(text_box(image, 290, 400)),
        feet_over(text_box(image, 790, 900)),
    ]
    assert all(s.source == "name tag" and not s.own for s in found)
    assert all(s.confidence > 0.75 for s in found)


def test_a_frame_without_tags_reads_no_one() -> None:
    reading = NameTagFinder().find(frame(blank()))
    assert reading.status is Status.READ
    assert reading.value == []


def test_the_status_bar_is_not_searched() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 750)  # in the bottom 80 rows
    assert NameTagFinder().find(frame(image)).value == []


def test_an_untrusted_frame_is_unsure() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    reading = NameTagFinder().find(frame(image, ok=False))
    assert reading.status is Status.UNSURE
    assert "moved" in reading.detail


def test_a_size_not_measured_is_unsure() -> None:
    reading = NameTagFinder().find(frame(blank((1600, 900))))
    assert reading.status is Status.UNSURE
    assert "1600" in reading.detail


# --------------------------------------------------------------------- our own tag


def test_ours_is_learned_from_three_sightings_where_the_minimap_puts_it() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    draw_tag(image, THEIRS, 800, 400)
    feet = feet_over(text_box(image, 290, 400))
    finder = NameTagFinder()
    assert taught(finder, image, (feet[0] + 6, feet[1] + 10)) == [False, False, True]
    assert finder.learned((1366, 768))
    assert finder.learned((1024, 768))  # same scale

    # Elsewhere, and beside another player's tag.
    later = blank()
    draw_tag(later, THEIRS, 550, 220)
    draw_tag(later, OURS, 600, 220)
    reading = finder.find(frame(later))
    assert reading.value is not None
    own = [s for s in reading.value if s.own]
    assert len(own) == 1
    assert own[0].feet == feet_over(text_box(later, 595, 700))
    assert own[0].confidence > 0.99
    assert reading.detail == ""


def test_nothing_is_learned_far_from_the_minimap() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    feet = feet_over(text_box(image, 290, 400))
    finder = NameTagFinder()
    assert taught(finder, image, (feet[0] + 40, feet[1])) == [False] * 3
    assert taught(finder, image, (feet[0], feet[1] - 60)) == [False] * 3
    assert not finder.learned((1366, 768))


def test_nothing_is_learned_where_two_tags_could_be_ours() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    draw_tag(image, THEIRS, 300, 430)
    feet = feet_over(text_box(image, 290, 400))
    finder = NameTagFinder()
    assert taught(finder, image, (feet[0], feet[1] + 15)) == [False] * 3


def test_ours_is_not_named_where_two_tags_look_like_it() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    finder = NameTagFinder()
    taught(finder, image, feet_over(text_box(image, 290, 400)))
    twice = blank()
    draw_tag(twice, OURS, 300, 400)
    draw_tag(twice, OURS, 900, 300)
    reading = finder.find(frame(twice))
    assert reading.value is not None
    assert len(reading.value) == 2
    assert not any(s.own for s in reading.value)
    assert reading.detail == "our tag not found"


@pytest.mark.parametrize("edge", ["right", "left"])
def test_ours_is_placed_when_the_client_edge_cuts_it(edge: str) -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    finder = NameTagFinder()
    taught(finder, image, feet_over(text_box(image, 290, 400)))
    whole = text_box(image, 290, 400)
    width = whole[2] - whole[0]
    # Draw it a quarter past the edge, on a wider picture cut to the client.
    wide = blank((1366 + 2 * width, 768))
    left = width + 1366 - 3 * width // 4 if edge == "right" else width - width // 4
    draw_tag(wide, OURS, left, 300)
    expected = text_box(wide, left - 10, left + width + 10)
    cut = np.ascontiguousarray(wide[:, width : width + 1366])
    reading = finder.find(frame(cut))
    assert reading.value is not None
    own = [s for s in reading.value if s.own]
    assert len(own) == 1
    assert own[0].feet == feet_over(
        (expected[0] - width, expected[1], expected[2] - width, expected[3])
    )


def test_learning_says_ours_can_be_told_apart_where_a_resized_tag_finds_it() -> None:
    """`learn_own`'s answer is `learned`'s: at a scale not learned yet, the tag
    learned at another, resized, already tells ours apart (fusion relies on
    it, #392)."""
    image = blank()
    draw_tag(image, OURS, 300, 400)
    finder = NameTagFinder()
    taught(finder, image, feet_over(text_box(image, 290, 400)))

    assert finder.learn_own(frame(blank((1920, 1080))), (500, 500)) is True
    assert NameTagFinder().learn_own(frame(blank((1920, 1080))), (500, 500)) is False


def test_ours_learned_at_1_to_1_is_found_on_an_upscaled_client() -> None:
    image = blank()
    draw_tag(image, OURS, 300, 400)
    finder = NameTagFinder()
    taught(finder, image, feet_over(text_box(image, 290, 400)))
    assert finder.learned((1920, 1080))

    play = blank()
    draw_tag(play, THEIRS, 500, 300)
    draw_tag(play, OURS, 900, 500)
    box = text_box(play, 890, 1000)
    upscaled = cv2.resize(play, (1920, 1080), interpolation=cv2.INTER_LINEAR)
    reading = finder.find(frame(np.asarray(upscaled, np.uint8)))
    assert reading.value is not None
    own = [s for s in reading.value if s.own]
    assert len(own) == 1
    scale = 1080 / 768
    expected = feet_over(box)
    # Within a client px of the 1:1 feet scaled up.
    assert abs(own[0].feet[0] - expected[0] * 1920 / 1366) <= 1.5
    assert abs(own[0].feet[1] - expected[1] * scale) <= 1.5
    assert len(reading.value) == 2  # theirs too


def test_a_resize_keeps_what_was_learned_at_each_scale() -> None:
    small = blank()
    draw_tag(small, OURS, 300, 400)
    finder = NameTagFinder()
    taught(finder, small, feet_over(text_box(small, 290, 400)))
    large = np.asarray(
        cv2.resize(small, (1920, 1080), interpolation=cv2.INTER_LINEAR), np.uint8
    )
    own = [s for s in finder.find(frame(large)).value or [] if s.own]
    assert len(own) == 1
    # Ours can be told apart all along, resized; the third sighting learns it
    # at this scale too.
    assert taught(finder, large, own[0].feet) == [True, True, True]
    assert 1080 / 768 in finder._learned  # pyright: ignore[reportPrivateUsage] - what was learned
    assert any(s.own for s in finder.find(frame(small)).value or [])


# ----------------------------------------------------------------------------- YOLO


class StubResult:
    def __init__(self, found: Sequence[Mapping[str, Any]]) -> None:
        self._found = found

    def summary(self) -> Sequence[Mapping[str, Any]]:
        return self._found


class StubModel:
    def __init__(self, found: Sequence[Mapping[str, Any]], results: int = 1) -> None:
        self.found = found
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, source: NDArray[np.uint8], *, conf: float, verbose: bool, iou: float
    ) -> list[StubResult]:
        self.calls.append(
            {"shape": source.shape, "conf": conf, "verbose": verbose, "iou": iou}
        )
        return [StubResult(self.found) for _ in range(self.results)]


def detection(
    name: str, box: tuple[float, float, float, float], confidence: float
) -> dict[str, Any]:
    """One entry of `Results.summary()`, as ultralytics writes it."""
    x1, y1, x2, y2 = box
    return {
        "name": name,
        "class": 0,
        "confidence": confidence,
        "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
    }


def test_yolo_characters_are_their_boxes_bottom_centres() -> None:
    model = StubModel(
        [
            detection("Character", (100.2, 50.0, 140.6, 120.4), 0.91),
            detection("Mob", (300, 300, 340, 360), 0.88),
            detection("Character", (500, 200, 530, 260), 0.7),
        ]
    )
    reading = YoloCharacterFinder(model).find(frame(blank()))
    assert reading.status is Status.READ
    assert reading.value == [
        CharacterSighting((120.4, 120.4), "yolo", 0.91, False, (100, 50, 141, 120)),
        CharacterSighting((515.0, 260.0), "yolo", 0.7, False, (500, 200, 530, 260)),
    ]
    assert model.calls == [
        {"shape": (768, 1366, 3), "conf": 0.65, "verbose": False, "iou": 0.3}
    ]


def test_yolo_threshold_is_passed_to_the_model() -> None:
    model = StubModel([])
    reading = YoloCharacterFinder(model, threshold=0.4).find(frame(blank()))
    assert reading.value == []
    assert model.calls[0]["conf"] == 0.4


def test_yolo_is_unsure_on_an_untrusted_frame_and_never_runs() -> None:
    model = StubModel([detection("Character", (1, 2, 3, 4), 0.9)])
    reading = YoloCharacterFinder(model).find(frame(blank(), ok=False))
    assert reading.status is Status.UNSURE
    assert model.calls == []


def test_yolo_is_unsure_unless_one_result_comes_back() -> None:
    reading = YoloCharacterFinder(StubModel([], results=2)).find(frame(blank()))
    assert reading.status is Status.UNSURE


def test_yolo_cannot_tell_ours_apart() -> None:
    finder = YoloCharacterFinder(StubModel([detection("Character", (1, 2, 3, 4), 0.9)]))
    assert finder.learn_own(frame(blank()), (2, 4)) is False
    assert not any(s.own for s in finder.find(frame(blank())).value or [])
