"""
Which way a cast of `MobsHitting` faces (#638, spec #631 § 6, "Facing"), as
pure functions of `attack_choice`: no `MobsHitting`, no detection.

The facing used to point at the mob closest to the box's centre, whatever the
skill reached (#51). It is now chosen among the sides where the attack fires:
`closest` by the horizontal distance from the feet to a counted mob's box
centre, `most` by how many mobs a side counts.
"""

from maple.decision_makers.attack_choice import choose
from maple.decision_makers.providers import Attack, Facing
from maple.model.characters.placed_reach import Placement, counted
from maple.model.characters.reach import Armed, Reach

#: Feet at (100, 300), 1:1, no chat in the way.
WHERE = Placement(feet=(100.0, 300.0), scale=(1.0, 1.0), bottom=600.0)
#: One-sided: 10 to 90 px in front, 60 px up from the feet.
SWING = Attack(Armed(object(), Reach(-90, -60, -10, 0)), 1)  # pyright: ignore[reportArgumentType] - the skill isn't read
#: Two-sided: 90 px each way.
AROUND = Attack(Armed(object(), Reach(-90, -60, 90, 0)), 1)  # pyright: ignore[reportArgumentType]


def mob(center_x: int) -> tuple[int, int, int, int]:
    """A 10 px wide mob standing on the feet's platform, centred on `center_x`."""
    return (center_x - 5, 260, center_x + 5, 300)


def test_a_one_sided_reach_is_counted_facing_left_and_facing_right() -> None:
    found = counted(SWING.reach, [mob(50), mob(30), mob(150)], WHERE)

    assert found == {"left": (mob(50), mob(30)), "right": (mob(150),)}


def test_a_two_sided_reach_is_counted_once() -> None:
    found = counted(AROUND.reach, [mob(50), mob(150)], WHERE)

    assert found == {None: (mob(50), mob(150))}


def test_only_a_side_that_fires_is_faced() -> None:
    """The closest mob is right, but only the left counts 2."""
    attack = Attack(SWING.armed, 2)

    choice = choose([attack], [mob(40), mob(30), mob(110)], WHERE, Facing.CLOSEST)

    assert choice is not None
    assert choice.direction == "left"


def test_closest_faces_the_counted_mob_nearest_the_feet_horizontally() -> None:
    choice = choose([SWING], [mob(40), mob(30), mob(130)], WHERE, Facing.CLOSEST)

    assert choice is not None
    assert choice.direction == "right"
    assert choice.mobs == (mob(130),)


def test_closest_faces_left_on_a_tie() -> None:
    choice = choose([SWING], [mob(150), mob(50)], WHERE, Facing.CLOSEST)

    assert choice is not None
    assert choice.direction == "left"


def test_most_faces_the_side_with_more_mobs() -> None:
    choice = choose([SWING], [mob(40), mob(30), mob(130)], WHERE, Facing.MOST)

    assert choice is not None
    assert choice.direction == "left"
    assert choice.mobs == (mob(40), mob(30))


def test_most_falls_back_to_closest_on_a_tie() -> None:
    choice = choose([SWING], [mob(30), mob(130)], WHERE, Facing.MOST)

    assert choice is not None
    assert choice.direction == "right"


def test_a_two_sided_attack_faces_nothing() -> None:
    choice = choose([AROUND], [mob(30), mob(130)], WHERE, Facing.MOST)

    assert choice is not None
    assert choice.direction is None


def test_no_attack_fires_without_a_mob_in_reach() -> None:
    assert choose([SWING, AROUND], [mob(500)], WHERE, Facing.CLOSEST) is None
