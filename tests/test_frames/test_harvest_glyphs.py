"""
`toolkit/harvest_glyphs.py` cuts glyphs, on synthetic ink and a synthetic
labeller: no frame, no client pixels, no font file.
"""

import json
from pathlib import Path

import numpy as np

from maple.screen.font import CHAT_GENERAL, COUNTDOWN, MINIMAP_TITLE
from toolkit import harvest_glyphs as tool


def glyph(rows: list[str]) -> np.ndarray:
    return np.array([[c == "#" for c in row] for row in rows])


LABELLER = {
    "h": glyph(["#..", "#..", "###", "#.#", "#.#"]),
    "i": glyph(["#", ".", "#", "#", "#"]),
    "I": glyph(["#", "#", "#", "#", "#"]),
    "l": glyph(["#", "#", "#", "#", "#"]),
}
ROWS = 9


def line(*placed: tuple[str, int], width: int = 30) -> np.ndarray:
    ink = np.zeros((ROWS, width), bool)
    for char, x in placed:
        mask = LABELLER[char]
        h, w = mask.shape
        ink[2 : 2 + h, x : x + w] |= mask
    return ink


def test_characters_drawn_alike_are_grouped_under_the_first() -> None:
    assert tool.alike(LABELLER) == {"I": "Il"}


def test_a_line_is_cut_into_whole_height_cells_labelled_by_the_font() -> None:
    harvest = tool.harvest_lines(
        [("one", line(("h", 1), ("i", 5), ("l", 9)))], LABELLER
    )

    assert harvest.problems == []
    assert harvest.labels == [("one", "hiI")]
    assert set(harvest.glyphs) == {"h", "i", "I"}
    assert harvest.glyphs["h"].shape == (ROWS, 3)
    assert (harvest.glyphs["h"][2:7] == LABELLER["h"]).all()
    assert harvest.sources["h"] == "one"


def test_ink_the_font_doesnt_explain_refuses_the_line() -> None:
    ink = line(("h", 1))
    ink[0, 20] = True

    harvest = tool.harvest_lines([("speck", ink)], LABELLER)

    assert harvest.glyphs == {}
    assert harvest.problems == ["speck: 1 ink pixel(s) no labelling glyph explains"]


def test_a_glyph_cut_differently_in_two_lines_is_a_problem() -> None:
    other = line(("h", 1))
    other[8, 2] = True  # under the h, in its cell, unexplained

    harvest = tool.harvest_lines([("a", line(("h", 1))), ("b", other)], LABELLER)

    assert any(p.startswith("b:") for p in harvest.problems)


def test_digits_are_cut_one_blob_each_labelled_by_the_text() -> None:
    ink = np.zeros((7, 12), bool)
    ink[1:6, 1:4] = glyph(["###", "..#", "###", "#..", "###"])
    ink[1:6, 6:8] = True

    harvest = tool.harvest_digits([("slot", ink, "21")])

    assert harvest.problems == []
    assert harvest.glyphs["1"].shape == (5, 2)
    assert harvest.glyphs["2"].sum() == 11


def test_blobs_that_dont_number_the_digits_refuse_the_box() -> None:
    ink = np.zeros((7, 12), bool)
    ink[1:6, 1:4] = True

    harvest = tool.harvest_digits([("slot", ink, "27")])

    assert harvest.glyphs == {}
    assert harvest.problems == ["slot: 1 blob(s) of ink for the 2 character(s) of '27'"]


def test_column_runs_are_cut_again_where_touching_letters_are_split() -> None:
    ink = np.zeros((3, 12), bool)
    ink[:, 1:3] = ink[:, 4:9] = ink[:, 10] = True

    assert tool.column_runs(ink) == [(1, 3), (4, 9), (10, 11)]
    assert tool.column_runs(ink, [6]) == [(1, 3), (4, 6), (6, 9), (10, 11)]
    assert tool.column_runs(ink, [3]) == [(1, 3), (4, 9), (10, 11)]


def test_a_title_line_is_cut_one_letter_per_run_labelled_by_the_text() -> None:
    ink = np.zeros((MINIMAP_TITLE.rows or 0, 14), bool)
    ink[0:8, 0:3] = True  # A
    ink[2:8, 4:6] = True  # b
    ink[0:8, 9:12] = True  # A again, after a word's gap

    harvest = tool.harvest_cut_lines([("line", ink, "Ab A", [])])

    assert harvest.problems == []
    assert harvest.labels == [("line", "Ab A")]
    assert set(harvest.glyphs) == {"A", "b"}
    assert harvest.glyphs["A"].shape == (MINIMAP_TITLE.rows, 3)


def test_touching_letters_need_their_split() -> None:
    ink = np.zeros((MINIMAP_TITLE.rows or 0, 8), bool)
    ink[0:8, 0:6] = True

    refused = tool.harvest_cut_lines([("line", ink, "Vi", [])])
    split = tool.harvest_cut_lines([("line", ink, "Vi", [4])])

    assert refused.problems == ["line: 1 run(s) of ink for the 2 letter(s) of 'Vi'"]
    assert split.problems == []
    assert split.glyphs["V"].shape[1] == 4
    assert split.glyphs["i"].shape[1] == 2


def test_a_harvest_that_misreads_its_own_source_is_reported() -> None:
    harvest = tool.Harvest(glyphs={"1": np.ones((5, 2), bool)})
    pixels = np.zeros((7, 10, 3), np.uint8)
    pixels[1:6, 2:4] = (14, 236, 252)

    assert tool.misreads(COUNTDOWN, harvest, [("ok", pixels, "1")]) == []
    assert tool.misreads(COUNTDOWN, harvest, [("bad", pixels, "7")]) == [
        "bad: read '1', labelled '7'"
    ]


def test_the_committed_sources_hold_no_pixels() -> None:
    """Frame names, boxes and digits only: chat text is never committed, since
    it carries other players' names."""
    for path in tool.SOURCES.glob("*.json"):
        sources = json.loads(path.read_text(encoding="utf-8"))
        for entry in sources[CHAT_GENERAL.name]:
            assert set(entry) == {"frame", "line"}
        for entry in sources[COUNTDOWN.name]:
            assert set(entry) == {"frame", "box", "text"}
            assert entry["text"].isdigit()
        for entry in sources.get(MINIMAP_TITLE.name, []):
            assert set(entry) <= {"frame", "line", "text", "splits"}
            assert entry["text"].replace(" ", "").isalpha()
    assert Path(tool.SOURCES / "v1.json").is_file()
