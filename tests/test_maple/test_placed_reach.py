"""
The one rule for "in reach" (#664): a mob's box overlaps the placed reach by at
least one **client** px on each axis, for both of its users.

- `MobsHitting` places a reach on screen, in client px (`choose`).
- The Hunting Area rotation places it at a spot of the map, in virtual px, and
  converts the one client px with the frame's scale (`reaches`).

Each is pinned at the edge: exactly one client px is in, just under it is out.
"""

from typing import Any

from maple.decision_makers.attack_choice import ClientBox, choose
from maple.decision_makers.providers import Attack, Facing
from maple.decision_makers.providers.sources.hunting_area import reaches
from maple.model.characters.placed_reach import Placement
from maple.model.characters.reach import Armed, Reach
from maple.screen.position import Camera

#: One-sided: 10 to 90 virtual px in front, 60 up from the feet.
SWING = Reach(-90, -60, -10, 0)
#: The one attack `choose` goes down; its skill isn't read.
ATTACK = Attack(Armed(object(), SWING), 1)  # pyright: ignore[reportArgumentType]

#: 2 client px per virtual px, feet at (1000, 500), the chat's top at 450:
#: facing left, the reach is x 820 to 980 and y 380 to 450 (cut at the chat).
ON_SCREEN = Placement.on_screen(
    (990, 440, 1010, 500), client_size=(2000, 1000), play_area=(1000, 500), chat_top=450
)

#: A 1920x1080 client's scale (`camera.PLAY_AREAS`): 1366x768 virtual px.
SCALE = (1920 / 1366, 1080 / 768)
#: One client px, in virtual px, on that client.
PX_X, PX_Y = 1366 / 1920, 768 / 1080


def fractional(*edges: float) -> ClientBox:
    """A detection box with fractional edges, as a box may have."""
    return edges  # pyright: ignore[reportReturnType] - fractional on purpose


def hit(mob: ClientBox) -> bool:
    """Whether `MobsHitting` would cast at the one mob on the frame."""
    return choose([ATTACK], [mob], ON_SCREEN, Facing.CLOSEST) is not None


# --- on screen, as `MobsHitting` places it ---------------------------------------------


def test_on_screen_exactly_one_client_px_of_overlap_is_in() -> None:
    assert hit((700, 400, 821, 500))  # x: 820 to 821
    assert hit((900, 300, 920, 381))  # y: 380 to 381


def test_on_screen_just_under_one_client_px_of_overlap_is_out() -> None:
    assert not hit(fractional(700, 400, 820.99, 500))
    assert not hit(fractional(900, 300, 920, 380.99))
    assert not hit((700, 400, 820, 500))  # touching, no overlap


def test_on_screen_the_cut_at_the_chat_is_the_reachs_bottom() -> None:
    assert hit((900, 449, 920, 470))  # y: 449 to the chat's top, 450
    assert not hit(fractional(900, 449.01, 920, 470))


def test_facing_right_the_edge_is_the_same() -> None:
    # Mirrored: x 1020 to 1180.
    assert hit((1179, 400, 1300, 500))
    assert not hit(fractional(1179.01, 400, 1300, 500))


# --- in virtual px, as the rotation places it ------------------------------------------


def box(*edges: float) -> Any:  # noqa: ANN401
    """A mob's box in virtual px."""
    return edges


def test_in_virtual_px_exactly_one_client_px_of_overlap_is_in() -> None:
    # The reach from (0, 0) facing left: x -90 to -10, y -60 to 0.
    assert reaches((0.0, 0.0), [box(-120, -40, -90 + PX_X, 0)], SWING, scale=SCALE) == 1
    assert (
        reaches((0.0, 0.0), [box(-50, -90, -40, -60 + PX_Y)], SWING, scale=SCALE) == 1
    )


def test_in_virtual_px_just_under_one_client_px_of_overlap_is_out() -> None:
    under_x = box(-120, -40, -90 + 0.99 * PX_X, 0)
    under_y = box(-50, -90, -40, -60 + 0.99 * PX_Y)

    assert reaches((0.0, 0.0), [under_x], SWING, scale=SCALE) == 0
    assert reaches((0.0, 0.0), [under_y], SWING, scale=SCALE) == 0


def test_in_virtual_px_the_threshold_follows_the_scale() -> None:
    # Three quarters of a virtual px: 1.5 client px at 2:1, 0.75 at 1:1.
    mob = box(-120, -40, -89.25, 0)

    assert reaches((0.0, 0.0), [mob], SWING, scale=(2.0, 2.0)) == 1
    assert reaches((0.0, 0.0), [mob], SWING, scale=(1.0, 1.0)) == 0


def test_in_virtual_px_a_reach_is_not_cut() -> None:
    where = Placement.in_virtual_px((0.0, 0.0), SCALE)

    assert where.place(Reach(-10, -10, 10, 50), None) == (-10.0, -10.0, 10.0, 50.0)


def test_in_virtual_px_one_client_px_placed_through_the_camera_is_in_at_every_column() -> (
    None
):
    # Boxes placed from whole client px land a hair either side of a whole
    # client px once scaled back: one client px of overlap still counts.
    camera = Camera(0, 0, 1.0, 2.0, (1366, 768))
    client = (1920, 1080)
    where = Placement.in_virtual_px((0.0, 0.0), camera.scale(client))

    def placed(x1: int, x2: int) -> Any:  # noqa: ANN401
        left, top = camera.to_virtual((x1, 0), client)
        right, bottom = camera.to_virtual((x2, 50), client)
        return (left, top, right, bottom)

    for x in range(50, 1870):
        assert where.touches(placed(x - 50, x + 1), placed(x, x + 50)), x
        assert not where.touches(placed(x - 50, x), placed(x, x + 50)), x
