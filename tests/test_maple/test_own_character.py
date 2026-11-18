import numpy as np
import pytest

from maple.model.characters import own_character as oc
from maple.model.characters.own_character import (
    Candidate,
    NameTagReader,
    OwnCharacterPicker,
)
from maple.screen.font import NAME_TAG, GlyphSet
from tests.test_maple.test_name_tag import GLYPHS, blank, draw_tag

IMAGE = np.zeros((400, 600, 3), np.uint8)
A = (100, 100, 140, 160)
B = (300, 100, 340, 160)


class StubReader:
    """Reads the tag by the strip's x position, so no glyph is matched."""

    def __init__(self, tags: dict[int, str]) -> None:
        self.tags = tags
        self.reads = 0
        self.seen: list[tuple[tuple[int, int], tuple[int, ...]]] = []

    def read_tag(self, strip: np.ndarray, client_size: tuple[int, int]) -> str:
        self.reads += 1
        self.seen.append((client_size, strip.shape[:2]))
        return self.tags.get(int(strip[0, 0, 0]), "")

    def fold(self, text: str) -> str:
        return text.casefold()


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
        strip_left = round(
            (box[0] + box[2]) / 2 - (box[2] - box[0] + oc.TAG_STRIP_EXTRA_WIDTH_PX) / 2
        )
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


def test_strip_is_scaled_on_an_upscaled_client() -> None:
    image = np.zeros((1080, 1920, 3), np.uint8)
    strip = oc.tag_strip(image, A, 1.5)
    assert strip is not None
    assert strip.shape[:2] == (
        round(oc.TAG_STRIP_HEIGHT_PX * 1.5),
        40 + round(oc.TAG_STRIP_EXTRA_WIDTH_PX * 1.5),
    )


def test_the_reader_is_given_the_client_size_and_a_strip_at_its_tag_scale() -> None:
    image = np.zeros((1080, 1920, 3), np.uint8)
    reader = StubReader({})
    picker = OwnCharacterPicker("Hero", reader)
    picker.pick(image, [Candidate(A, 0.7), Candidate(B, 0.9)])
    height = round(oc.TAG_STRIP_HEIGHT_PX * 1080 / 768)
    assert {seen for seen in reader.seen} == {
        ((1920, 1080), (height, 40 + round(oc.TAG_STRIP_EXTRA_WIDTH_PX * 1080 / 768)))
    }


def test_a_picker_with_no_reader_keeps_the_box_by_its_fallbacks() -> None:
    _, image, _, _ = make({A[0]: "Hero"})
    picker = OwnCharacterPicker("Hero")
    assert picker.pick(image, [Candidate(A, 0.7), Candidate(B, 0.9)]) == B


def test_letters_the_font_draws_alike_fold_as_one() -> None:
    reader = NameTagReader(GlyphSet(NAME_TAG, GLYPHS, alike={"I": "Il"}))
    assert reader.fold("BiII") == reader.fold("Bill") == reader.fold("BilI")
    assert reader.fold("Bill") != reader.fold("Bell")


def test_the_tag_read_with_glyphs_picks_ours() -> None:
    """Two characters, each over a tag drawn with made-up glyphs: ours is the
    less confident one, and is kept by its tag."""
    image = blank(width=300, height=120)
    ours, theirs = (40, 20, 80, 70), (180, 20, 220, 70)
    # A tag's cell 5 px under the feet, as the client draws it (`TAG_TO_FEET`).
    draw_tag(image, "bAob", 47, top=75)
    draw_tag(image, "pAoA", 186, top=75)
    picker = OwnCharacterPicker("BAOB", NameTagReader(GlyphSet(NAME_TAG, GLYPHS)))
    assert picker.pick(image, [Candidate(ours, 0.6), Candidate(theirs, 0.9)]) == ours
