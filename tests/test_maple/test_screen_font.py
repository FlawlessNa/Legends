"""
Harvested glyph sets (`maple.screen.font`), on synthetic glyphs and frames the
test draws itself: no client pixels, and no font file.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from maple.screen.font import (
    CHAT_GENERAL,
    COUNTDOWN,
    GLYPH_SETS,
    MANIFEST,
    GlyphSet,
    GlyphsMissing,
    glyph_file,
    load_glyph_set,
    save_glyph_set,
)

RNG = np.random.default_rng(313)


def glyph(rows: list[str]) -> np.ndarray:
    return np.array([[c == "#" for c in row] for row in rows])


DIGITS = {
    "1": glyph([".#.", "##.", ".#.", ".#.", "###"]),
    "2": glyph(["###", "..#", "###", "#..", "###"]),
    "7": glyph(["###", "..#", ".#.", ".#.", ".#."]),
}


def cell(rows: list[str]) -> np.ndarray:
    """A chat glyph: a whole cell of `CHAT_GENERAL.rows` rows, ink near the
    middle, as a line's glyphs are cut."""
    out = np.zeros((CHAT_GENERAL.rows or 0, len(rows[0])), bool)
    out[4 : 4 + len(rows)] = glyph(rows)
    return out


LETTERS = {
    "h": cell(["#..", "#..", "###", "#.#", "#.#"]),
    "i": cell(["#", ".", "#", "#", "#"]),
    "I": cell(["#", "#", "#", "#", "#"]),
}


def draw(
    background: np.ndarray, glyphs: list[tuple[np.ndarray, int]], bgr: tuple[int, ...]
) -> np.ndarray:
    pixels = background.copy()
    for mask, x in glyphs:
        h, w = mask.shape
        pixels[:h, x : x + w][mask] = bgr
    return pixels


# Saving and loading.


def test_a_saved_set_loads_back_the_same(tmp_path: Path) -> None:
    save_glyph_set(COUNTDOWN, DIGITS, {"1": "f009 box 1331,13"}, root=tmp_path)

    loaded = load_glyph_set(COUNTDOWN.name, tmp_path)

    assert loaded.spec == COUNTDOWN
    assert set(loaded.glyphs) == set(DIGITS)
    for char, mask in DIGITS.items():
        assert (loaded.glyphs[char] == mask).all()
    manifest = json.loads((tmp_path / "countdown" / MANIFEST).read_text("utf-8"))
    assert manifest["glyphs"]["1"] == {
        "file": "U+0031.png",
        "source": "f009 box 1331,13",
    }


def test_alike_characters_are_kept(tmp_path: Path) -> None:
    save_glyph_set(CHAT_GENERAL, LETTERS, {}, {"I": "Il"}, root=tmp_path)

    assert load_glyph_set(CHAT_GENERAL.name, tmp_path).alike == {"I": "Il"}


def test_bearings_are_kept_for_the_glyphs_that_have_them(tmp_path: Path) -> None:
    save_glyph_set(CHAT_GENERAL, LETTERS, {}, root=tmp_path, bearings={"h": (1, 2)})

    assert load_glyph_set(CHAT_GENERAL.name, tmp_path).bearings == {"h": (1, 2)}


def test_saving_again_replaces_the_set(tmp_path: Path) -> None:
    save_glyph_set(COUNTDOWN, DIGITS, {}, root=tmp_path)
    save_glyph_set(COUNTDOWN, {"7": DIGITS["7"]}, {}, root=tmp_path)

    assert set(load_glyph_set(COUNTDOWN.name, tmp_path).glyphs) == {"7"}
    assert [p.name for p in (tmp_path / "countdown").glob("U+*")] == ["U+0037.png"]


def test_a_glyph_file_is_named_by_its_code_point() -> None:
    assert glyph_file("@") == "U+0040.png"
    assert glyph_file(":") == "U+003A.png"


def test_a_set_not_harvested_is_missing_saying_how_to_harvest(
    tmp_path: Path,
) -> None:
    with pytest.raises(GlyphsMissing, match="toolkit.harvest_glyphs"):
        load_glyph_set(COUNTDOWN.name, tmp_path)


def test_a_glyph_file_gone_is_missing(tmp_path: Path) -> None:
    folder = save_glyph_set(COUNTDOWN, DIGITS, {}, root=tmp_path)
    (folder / glyph_file("2")).unlink()

    with pytest.raises(GlyphsMissing, match="U\\+0032.png"):
        load_glyph_set(COUNTDOWN.name, tmp_path)


def test_a_malformed_manifest_is_missing(tmp_path: Path) -> None:
    folder = save_glyph_set(COUNTDOWN, DIGITS, {}, root=tmp_path)
    (folder / MANIFEST).write_text("{", encoding="utf-8")

    with pytest.raises(GlyphsMissing, match="malformed"):
        load_glyph_set(COUNTDOWN.name, tmp_path)


def test_a_chat_glyph_of_the_wrong_height_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rows"):
        save_glyph_set(CHAT_GENERAL, {"1": DIGITS["1"]}, {}, root=tmp_path)


def test_an_unknown_set_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        load_glyph_set("chat-whisper", tmp_path)


def test_every_set_is_registered_by_its_name() -> None:
    assert all(name == spec.name for name, spec in GLYPH_SETS.items())


# Reading.


def test_chat_text_is_read_exactly_over_any_background() -> None:
    rows = CHAT_GENERAL.rows or 0
    background = RNG.integers(0, 250, (rows, 40, 3), dtype=np.uint8)
    pixels = draw(
        background,
        [(LETTERS["h"], 2), (LETTERS["i"], 6), (LETTERS["I"], 12)],
        (255, 255, 255),
    )

    assert GlyphSet(CHAT_GENERAL, LETTERS).read(pixels) == "hi I"


def test_chat_ink_is_exactly_white() -> None:
    rows = CHAT_GENERAL.rows or 0
    background = np.full((rows, 20, 3), 30, np.uint8)
    pixels = draw(background, [(LETTERS["h"], 2)], (254, 255, 255))

    assert GlyphSet(CHAT_GENERAL, LETTERS).read(pixels) == ""


UNHARVESTED = cell(["#.#", "#.#", ".#.", "#.#", "#.#"])
"""A letter the set doesn't have."""


def white_line(glyphs: list[tuple[np.ndarray, int]], width: int = 40) -> np.ndarray:
    background = np.full((CHAT_GENERAL.rows or 0, width, 3), 30, np.uint8)
    return draw(background, glyphs, (255, 255, 255))


def test_a_letter_with_no_glyph_reads_as_one_unread_character_in_its_place() -> None:
    pixels = white_line([(LETTERS["h"], 2), (UNHARVESTED, 6), (LETTERS["i"], 10)])

    assert GlyphSet(CHAT_GENERAL, LETTERS).read_marked(pixels) == "h\ufffdi"
    assert GlyphSet(CHAT_GENERAL, LETTERS).read_all(pixels) is None


def test_an_unread_letter_keeps_the_spaces_around_it() -> None:
    pixels = white_line([(LETTERS["h"], 2), (UNHARVESTED, 9), (LETTERS["i"], 16)])

    assert GlyphSet(CHAT_GENERAL, LETTERS).read_marked(pixels) == "h \ufffd i"


def test_a_letter_whose_columns_hold_a_harvested_glyph_is_one_unread_letter() -> None:
    """`I` matches the stem of a letter the set lacks, exactly; the rest of the
    letter touches it, so the whole is one letter, not `I` and another."""
    stem_and_foot = cell(["#.", "#.", "#.", "#.", "##"])

    pixels = white_line([(stem_and_foot, 2), (LETTERS["i"], 6)])

    assert GlyphSet(CHAT_GENERAL, LETTERS).read_marked(pixels) == "\ufffdi"


def test_harvested_letters_that_touch_are_both_read() -> None:
    pixels = white_line([(LETTERS["h"], 2), (LETTERS["i"], 5)])

    assert GlyphSet(CHAT_GENERAL, LETTERS).read_marked(pixels) == "hi"


def test_a_line_whose_letters_are_all_harvested_reads_as_read_all_reads_it() -> None:
    pixels = white_line([(LETTERS["h"], 2), (LETTERS["i"], 6), (LETTERS["I"], 12)])
    glyphs = GlyphSet(CHAT_GENERAL, LETTERS)

    assert glyphs.read_marked(pixels) == glyphs.read_all(pixels) == "hi I"


BEARINGS = {"h": (1, 1), "i": (2, 2), "I": (0, 0)}
"""Made up: `i` drawn with more room around it than `I`."""


def test_a_gap_no_wider_than_the_letters_bearings_is_not_a_space() -> None:
    """3 columns, a plain space by `space_gap`, are `h`'s and `i`'s bearings."""
    pixels = white_line([(LETTERS["h"], 2), (LETTERS["i"], 8)])
    glyphs = GlyphSet(CHAT_GENERAL, LETTERS, bearings=BEARINGS)

    assert glyphs.read_marked(pixels) == glyphs.read_all(pixels) == "hi"


def test_a_gap_wider_than_the_bearings_by_half_a_space_is_a_space() -> None:
    pixels = white_line([(LETTERS["h"], 2), (LETTERS["I"], 8)])
    glyphs = GlyphSet(CHAT_GENERAL, LETTERS, bearings=BEARINGS)

    assert glyphs.read_marked(pixels) == "h I"


def test_next_to_an_unread_letter_a_space_is_a_plain_gap() -> None:
    pixels = white_line([(LETTERS["h"], 2), (UNHARVESTED, 8), (LETTERS["i"], 12)])
    glyphs = GlyphSet(CHAT_GENERAL, LETTERS, bearings=BEARINGS)

    assert glyphs.read_marked(pixels) == "h �i"


def test_countdown_digits_are_read_whatever_the_yellow_is_blended_with() -> None:
    background = np.zeros((7, 20, 3), np.uint8)  # the digits' dark outline
    pixels = draw(background, [(DIGITS["2"], 2), (DIGITS["7"], 7)], (14, 236, 252))
    pixels[:5, 7:10][DIGITS["7"]] = (2, 200, 230)  # duller over another icon
    pixels[1, 3] = (14, 120, 140)  # one pixel of the 2 blended away

    assert GlyphSet(COUNTDOWN, DIGITS).read(pixels) == "27"


def test_a_countdown_too_far_from_any_digit_reads_nothing() -> None:
    background = np.zeros((7, 10, 3), np.uint8)
    pixels = draw(background, [(np.ones((5, 3), bool), 2)], (14, 236, 252))

    assert GlyphSet(COUNTDOWN, DIGITS).read(pixels) == ""
