import numpy as np
import pytest

from maple.model.characters import own_character as oc
from maple.model.characters.own_character import Candidate, OwnCharacterPicker

IMAGE = np.zeros((400, 600, 3), np.uint8)
A = (100, 100, 140, 160)
B = (300, 100, 340, 160)


class StubReader:
    """Reads the tag by the strip's x position, so no OCR runs."""

    def __init__(self, tags: dict[int, str]) -> None:
        self.tags = tags
        self.reads = 0

    def read_tag(self, strip: np.ndarray) -> str:
        self.reads += 1
        return self.tags.get(int(strip[0, 0, 0]), "")


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def make(
    tags: dict[int, str] | None = None,
) -> tuple[OwnCharacterPicker, np.ndarray, StubReader, Clock]:
    image = IMAGE.copy()
    # Mark each strip's first pixel with the box's x1, which the stub reads.
    for box in (A, B):
        strip_left = round((box[0] + box[2]) / 2 - (box[2] - box[0] + 40) / 2)
        image[box[3], strip_left, 0] = box[0] % 256
    reader = StubReader(tags or {})
    clock = Clock()
    return OwnCharacterPicker("Hero", reader, clock), image, reader, clock


def test_tag_reading_the_ign_wins_over_confidence() -> None:
    picker, image, _, _ = make({A[0]: "Hero", B[0]: "Other"})
    assert picker.pick(image, [Candidate(A, 0.7), Candidate(B, 0.9)]) == A


def test_unreadable_tag_falls_back_to_the_closest_to_the_last_kept() -> None:
    picker, image, reader, _ = make({A[0]: "Hero"})
    assert picker.pick(image, [Candidate(A, 0.7), Candidate(B, 0.9)]) == A
    reader.tags = {}
    assert picker.pick(image, [Candidate(A, 0.6), Candidate(B, 0.9)]) == A


def test_no_history_falls_back_to_the_most_confident() -> None:
    picker, image, _, _ = make()
    assert picker.pick(image, [Candidate(A, 0.7), Candidate(B, 0.9)]) == B


def test_continuity_has_a_distance_limit() -> None:
    picker, image, _, _ = make()
    picker.pick(image, [Candidate(A, 0.9)])
    far = (A[0] + 300, A[1], A[2] + 300, A[3])
    assert oc.TRACK_MAX_DISTANCE_PX < 300
    assert picker.pick(image, [Candidate(far, 0.5), Candidate(B, 0.8)]) == B


def test_continuity_has_an_age_limit() -> None:
    picker, image, _, clock = make()
    picker.pick(image, [Candidate(A, 0.9)])
    clock.now = oc.TRACK_MAX_AGE_S + 1
    assert picker.pick(image, [Candidate(A, 0.5), Candidate(B, 0.8)]) == B


def test_continuity_holds_within_the_age_limit() -> None:
    picker, image, _, clock = make()
    picker.pick(image, [Candidate(A, 0.9)])
    clock.now = oc.TRACK_MAX_AGE_S - 1
    assert picker.pick(image, [Candidate(A, 0.5), Candidate(B, 0.8)]) == A


def test_one_candidate_reads_nothing() -> None:
    picker, image, reader, _ = make({A[0]: "Other"})
    assert picker.pick(image, [Candidate(A, 0.5)]) == A
    assert reader.reads == 0


def test_no_candidate_is_none() -> None:
    picker, image, _, _ = make()
    assert picker.pick(image, []) is None


@pytest.mark.parametrize("box", [(0, 0, 40, 400), (0, 395, 40, 400)])
def test_strip_off_the_image_is_skipped(box: oc.Box4) -> None:
    assert oc.tag_strip(IMAGE, box) is None


def test_strip_geometry() -> None:
    strip = oc.tag_strip(IMAGE, A)
    assert strip is not None
    assert strip.shape[:2] == (oc.TAG_STRIP_HEIGHT_PX, 40 + oc.TAG_STRIP_EXTRA_WIDTH_PX)
