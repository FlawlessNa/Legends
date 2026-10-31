"""Matching primitives and Reading, on synthetic images only."""

import dataclasses
import time

import numpy as np
import pytest

from botting.screen import (
    Reading,
    Status,
    find_glyphs,
    match,
    match_best,
    matches_at,
    read_glyphs,
)


def make_glyph(seed: int, w: int = 5, h: int = 7) -> np.ndarray:
    """A random RGBA glyph: ~60% opaque pixels, strongly coloured."""
    rng = np.random.default_rng(seed)
    g = np.zeros((h, w, 4), np.uint8)
    g[:, :, :3] = rng.integers(0, 256, (h, w, 3))
    g[:, :, 3] = np.where(rng.random((h, w)) < 0.6, 255, 0)
    g[0, 0, 3] = 255
    return g


def stamp(canvas: np.ndarray, sprite: np.ndarray, x: int, y: int) -> None:
    h, w = sprite.shape[:2]
    opaque = sprite[:, :, 3] == 255
    view = canvas[y : y + h, x : x + w]
    view[opaque] = sprite[:, :, 2::-1][opaque]


def blank(w: int = 60, h: int = 30) -> np.ndarray:
    return np.full((h, w, 3), 40, np.uint8)


def test_exact_hit_at_planted_position() -> None:
    sprite, hay = make_glyph(1), blank()
    stamp(hay, sprite, 17, 9)
    hits = match(hay, sprite)
    assert [(h.x, h.y, h.error) for h in hits] == [(17, 9, 0.0)]
    best = match_best(hay, sprite)
    assert best is not None
    assert (best.x, best.y) == (17, 9)


def test_match_best_none_when_absent() -> None:
    assert match_best(blank(), make_glyph(1)) is None


def test_one_pixel_off_by_8_is_rejected() -> None:
    sprite, hay = make_glyph(2), blank()
    stamp(hay, sprite, 10, 10)
    ys, xs = np.nonzero(sprite[:, :, 3] == 255)
    hay[10 + ys[3], 10 + xs[3], 1] += 8
    assert match(hay, sprite) == []
    hay[10 + ys[3], 10 + xs[3], 1] -= 6  # off by 2: 4/count <= 0.5
    assert len(match(hay, sprite)) == 1


def test_alpha_251_to_254_does_not_count() -> None:
    sprite, hay = make_glyph(3), blank()
    stamp(hay, sprite, 5, 5)
    faint = sprite.copy()
    faint[0, 1] = (200, 0, 0, 254)  # would mismatch if it counted
    faint[1, 0] = (0, 200, 0, 251)
    assert len(match(hay, faint)) == 1


def test_no_opaque_pixel_raises() -> None:
    sprite = make_glyph(4)
    sprite[:, :, 3] = 254
    with pytest.raises(ValueError, match="alpha 255"):
        match(blank(), sprite)


def test_region_offset_applied_and_limits_search() -> None:
    sprite, hay = make_glyph(5), blank()
    stamp(hay, sprite, 8, 3)
    stamp(hay, sprite, 40, 20)
    hits = match(hay, sprite, region=(30, 12, 30, 18))
    assert [(h.x, h.y) for h in hits] == [(40, 20)]


def test_region_smaller_than_sprite_or_outside_is_empty() -> None:
    sprite = make_glyph(5)
    assert match(blank(), sprite, region=(0, 0, 3, 3)) == []
    assert match(blank(), sprite, region=(500, 500, 10, 10)) == []


CHARS = "0123456789[]/,.%"


def glyph_set() -> dict[str, np.ndarray]:
    return {c: make_glyph(100 + i) for i, c in enumerate(CHARS)}


def draw(text: str, glyphs: dict[str, np.ndarray]) -> np.ndarray:
    strip = np.full((16, 6 * len(text) + 4, 3), 40, np.uint8)
    for i, c in enumerate(text):
        stamp(strip, glyphs[c], 2 + 6 * i, 4)
    return strip


def test_strip_of_digits_and_punctuation_reads_exactly() -> None:
    glyphs = glyph_set()
    text = "[1,234/5,678].90%"
    assert read_glyphs(draw(text, glyphs), glyphs) == text
    assert read_glyphs(draw(CHARS, glyphs), glyphs) == CHARS


def test_overlapping_larger_glyph_wins() -> None:
    small = make_glyph(7, 3, 5)
    big = np.zeros((5, 6, 4), np.uint8)
    big[:, :, :3] = 200
    big[:, :, 3] = 255
    big[:, 3:, :3] = 90
    # the small glyph is the right half of the big one, so it hits inside it
    big[:5, 3:6, :3] = small[:5, :3, :3]
    big[:5, 3:6, 3] = 255
    small[:, :, 3] = 255
    strip = np.full((10, 20, 3), 40, np.uint8)
    stamp(strip, big, 4, 2)
    assert len(match(strip, small)) >= 1
    assert read_glyphs(strip, {"s": small, "B": big}) == "B"


def test_reading_helpers_and_invariants() -> None:
    r = Reading.read(5, 1.0)
    assert (r.value, r.status) == (5, Status.READ)
    for make in (Reading.absent, Reading.covered, Reading.unsure):
        x = make(2.0, "why")
        assert x.value is None
        assert x.detail == "why"
        assert x.frame_time == 2.0
    assert Reading.absent(0.0).status is Status.ABSENT
    assert Reading.covered(0.0).status is Status.COVERED
    assert Reading.unsure(0.0).status is Status.UNSURE
    with pytest.raises(ValueError, match="needs a value"):
        Reading(None, Status.READ, 0.0)
    with pytest.raises(ValueError, match="cannot carry"):
        Reading(3, Status.ABSENT, 0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.value = 6  # type: ignore[misc]


@pytest.mark.lab
def test_glyph_over_strip_runs_under_1ms() -> None:
    glyph = make_glyph(9)
    strip = np.full((16, 340, 3), 40, np.uint8)
    stamp(strip, glyph, 100, 4)
    match(strip, glyph)
    runs = 200
    t0 = time.perf_counter()
    for _ in range(runs):
        match(strip, glyph)
    ms = (time.perf_counter() - t0) / runs * 1000
    assert ms < 1.0, f"match 5x7 over 340x16 took {ms:.3f} ms"


def test_matches_at_agrees_with_match_at_one_position() -> None:
    sprite, hay = make_glyph(1), blank()
    stamp(hay, sprite, 17, 9)

    assert matches_at(hay, sprite, 17, 9)
    assert not matches_at(hay, sprite, 18, 9)
    # One opaque pixel off by 8 in one channel is rejected, as `match` does.
    y, x = np.argwhere(sprite[:, :, 3] == 255)[0]
    hay[9 + y, 17 + x, 0] = (int(hay[9 + y, 17 + x, 0]) + 8) % 256
    assert not matches_at(hay, sprite, 17, 9)
    assert match(hay, sprite) == []


@pytest.mark.parametrize(("x", "y"), [(-1, 0), (0, -1), (56, 0), (0, 25)])
def test_matches_at_is_false_when_the_sprite_would_leave_the_image(
    x: int, y: int
) -> None:
    sprite = make_glyph(2)
    hay = blank()
    stamp(hay, sprite, 0, 0)

    assert not matches_at(hay, sprite, x, y)


def test_find_glyphs_says_where_each_glyph_is() -> None:
    glyphs = {"a": make_glyph(3), "b": make_glyph(4)}
    hay = blank()
    stamp(hay, glyphs["a"], 4, 6)
    stamp(hay, glyphs["b"], 11, 6)

    hits = find_glyphs(hay, glyphs)

    assert [(h.name, h.x, h.y, h.width, h.height) for h in hits] == [
        ("a", 4, 6, 5, 7),
        ("b", 11, 6, 5, 7),
    ]
    assert read_glyphs(hay, glyphs) == "ab"
