"""
The footholds and ropes drawn on objects and tiles (`catalogue.geometry`),
ported from the v83 module, and the raw-tree reader they stand on
(`catalogue.trees`). The trees are the raw layer's JSON, written by hand.
"""

import pytest

from game_data.catalogue import CatalogueError
from game_data.catalogue.geometry import (
    Climb,
    Segment,
    climbs,
    footholds,
    placed,
    polylines,
    segments,
)
from game_data.catalogue.trees import Tree
from game_data.extraction import Json


def vector(x: int, y: int) -> dict[str, Json]:
    return {"$type": "vector", "x": x, "y": y}


def convex(*points: tuple[int, int]) -> dict[str, Json]:
    found: dict[str, Json] = {"$type": "convex"}
    for n, point in enumerate(points):
        found[str(n)] = vector(*point)
    return found


def canvas(**children: Json) -> dict[str, Json]:
    return {"$type": "canvas", "image": "ab" * 32, "w": 1, "h": 1} | children


def node(value: Json, path: str = "a") -> Tree:
    """`value` as the child `a` of an image's root."""
    root: dict[str, Json] = {path: value}
    return Tree.of("Map/Obj/x.img", root).at(path)


# --- segments and placing ---------------------------------------------------


def test_a_polyline_is_one_segment_per_pair_of_points() -> None:
    assert segments([(0, 0), (10, 5), (20, 5)]) == [
        Segment(0, 0, 10, 5),
        Segment(10, 5, 20, 5),
    ]
    assert segments([(0, 0)]) == []
    assert segments([]) == []


def test_points_are_placed_at_the_item_and_mirrored_when_flipped() -> None:
    points = [(-10, 0), (5, -3)]

    assert placed(points, 100, 50, False) == [(90, 50), (105, 47)]
    assert placed(points, 100, 50, True) == [(110, 50), (95, 47)]


# --- footholds ---------------------------------------------------------------


def test_a_foothold_is_one_convex_or_a_sub_property_of_them() -> None:
    one = node(convex((0, 0), (1, 1)))
    several = node({"0": convex((0, 0), (1, 1)), "1": convex((2, 2), (3, 3), (4, 4))})

    assert polylines(one) == [[(0, 0), (1, 1)]]
    assert polylines(several) == [[(0, 0), (1, 1)], [(2, 2), (3, 3), (4, 4)]]


def test_an_objects_footholds_come_from_its_frame_and_from_itself() -> None:
    """Classic sometimes puts an object's foothold beside its frames."""
    obj = node(
        {
            "0": canvas(foothold=convex((0, 0), (10, 0))),
            "foothold": convex((0, -20), (0, -30)),
        }
    )
    frame = obj.at("0")

    found = footholds([frame, obj], 100, 200, False)

    assert found == [Segment(100, 200, 110, 200), Segment(100, 180, 100, 170)]


def test_a_tile_without_a_foothold_has_none() -> None:
    assert footholds([node(canvas(z=0))], 0, 0, False) == []


def test_an_empty_convex_draws_nothing() -> None:
    assert footholds([node(canvas(foothold=convex()))], 0, 0, False) == []


def test_a_convex_nobody_knows_is_an_error_naming_it() -> None:
    with pytest.raises(CatalogueError) as raised:
        footholds([node(canvas(seat=convex((0, 0))))], 0, 0, False)

    assert str(raised.value) == (
        "image Map/Obj/x.img, node a/seat: a convex nobody knows the meaning of"
    )


def test_a_numbered_convex_on_a_frame_is_read_as_nothing() -> None:
    """One object in the client has one, beside no `foothold`."""
    frame = node(canvas(**{"0": convex((0, 0), (5, 5))}))

    assert footholds([frame], 0, 0, False) == []
    assert climbs([frame], 0, 0, False) == []


# --- ropes and ladders -------------------------------------------------------


@pytest.mark.parametrize("name", ["ladder", "rope", "laddeer"])
def test_a_ladder_or_rope_is_a_vertical_line_placed_at_the_object(name: str) -> None:
    frame = node(canvas(**{name: convex((2, -40), (2, 0))}))

    assert climbs([frame], 600, -50, False) == [Climb(602, -90, -50)]
    assert climbs([frame], 600, -50, True) == [Climb(598, -90, -50)]


def test_a_ladder_that_isnt_two_points_with_one_x_is_an_error() -> None:
    frame = node(canvas(ladder=convex((0, 0), (5, 10))))

    with pytest.raises(CatalogueError, match="node a/ladder: a ladder should be two"):
        climbs([frame], 0, 0, False)


# --- reading trees -----------------------------------------------------------


def test_a_link_is_followed_from_its_parent_inside_the_image() -> None:
    root: Json = {"frames": {"0": canvas(delay=5), "1": {"$type": "uol", "path": "0"}}}
    link = Tree.of("i.img", root).at("frames").at("1")

    assert link.resolved().path == "frames/0"
    assert link.resolved().integer("delay") == 5


def test_a_link_out_of_the_image_or_to_nothing_is_an_error() -> None:
    root: Json = {
        "up": {"$type": "uol", "path": "../../x"},
        "none": {"$type": "uol", "path": "missing"},
    }
    tree = Tree.of("i.img", root)

    with pytest.raises(CatalogueError, match="node up: the link '../../x' leaves"):
        tree.at("up").resolved()
    with pytest.raises(CatalogueError, match="node none: the link 'missing' names"):
        tree.at("none").resolved()


def test_integers_are_ints_shorts_longs_or_strings_of_digits() -> None:
    tree = Tree.of(
        "i.img",
        {
            "int": 1,
            "short": {"$type": "short", "value": -2},
            "long": {"$type": "long", "value": 2**40},
            "digits": "0100100",
            "word": "x",
            "double": 1.0,
        },
    )

    assert [tree.integer(k) for k in ("int", "short", "long", "digits")] == [
        1,
        -2,
        2**40,
        100100,
    ]
    with pytest.raises(CatalogueError, match="node word: it is a string, not an int"):
        tree.integer("word")
    with pytest.raises(CatalogueError, match="node double: it is a double, not an int"):
        tree.integer("double")
    with pytest.raises(CatalogueError, match="i.img: it has no child 'gone'"):
        tree.integer("gone")
    assert tree.integer_or("gone", 7) == 7
    assert tree.optional_integer("gone") is None


def test_a_canvas_own_keys_arent_its_children() -> None:
    frame = node(canvas(origin=vector(3, 4)))

    assert [name for name, _ in frame.children()] == ["origin"]
    assert frame.get("w") is None
    assert frame.canvas_image() == "ab" * 32
    assert frame.origin() == (3, 4)
