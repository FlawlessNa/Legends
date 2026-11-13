"""
The decision makers on virtual positions (#398), against synthetic `WorldMap`s:
the rotation's targets on platforms a Path reaches, the mob-spawn check's
wander, and the ladder check before a cast. No game client, no game data store.
"""

import asyncio
import random
from collections.abc import Callable

import pytest

from botting.core import BotData
from botting.screen import Reading
from maple.decision_makers.ensure_mob_still_spawn import CheckMobsStillSpawn
from maple.decision_makers.mixins import MovementsMixin, NextTargetMixin
from maple.decision_makers.mixins._rotation_mixins import read_position
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from maple.telemetry_events import MOVEMENT_TARGET_REACHED
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.fixture_maps import portal_pair, rope_grab

#: A floor 0-300 at y 0, a floor 600-900 at y -400, and a portal from the
#: lower to the upper only: from the upper floor, the lower one is unreachable.
PORTALS = WorldMap.from_map_data(portal_pair())
LOWER, UPPER = PORTALS.platforms


class _Character:
    skills: dict[str, object] = {}  # noqa: RUF012


class _Rotation(MovementsMixin, NextTargetMixin):
    """A rotation's target and planning halves, over a real `BotData`."""

    def __init__(self, data: BotData) -> None:
        self.data = data


def _data(world: WorldMap, at: Callable[[], Reading[VirtualPosition]]) -> BotData:
    data = BotData("T")
    data.set_static("handle", 0)
    data.set_static("ign", "T")
    data.set_static("character", _Character())
    data.set_static("world_map", world)
    data.set_static("game_physics", corpus.LAB_PHYSICS_VALUES)
    data.set_static("speed_multiplier", 1.0)
    data.set_static("jump_multiplier", 1.0)
    data.create_attribute("current_position", at, initial_value=at())
    data.update_attribute("current_position")  # read once, as a Session has
    return data


def _fused(x: float, y: float) -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(x, y, PositionSource.FUSED), 0.0)


def _rotation(at: Callable[[], Reading[VirtualPosition]]) -> _Rotation:
    """Targets made before planning: the first is drawn blind, as `Rotation` does."""
    rotation = _Rotation(_data(PORTALS, at))
    rotation._create_rotation_attributes()
    rotation._create_pathing_attributes(1.0)
    return rotation


def test_a_rotation_needs_the_bots_map() -> None:
    data = BotData("T")
    data.set_static("world_map", None)

    with pytest.raises(ValueError, match="map isn't known"):
        _Rotation(data)._create_rotation_attributes()


def test_the_first_target_is_drawn_on_any_platform_before_a_position_is_read() -> None:
    random.seed(0)
    unread = Reading.unsure(0.0, "not read yet")

    targets = {_rotation(lambda: unread).data.next_target for _ in range(30)}

    on = {PORTALS.platform_at(t) for t in targets}
    assert on == {LOWER, UPPER}


def test_a_blind_target_no_path_reaches_is_drawn_again_once_placed() -> None:
    """
    From the upper floor nothing reaches the lower one: a first target drawn
    there, before the position was known, is replaced on the next update.
    """
    random.seed(1)
    for _ in range(20):
        rotation = _rotation(lambda: _fused(750.0, -400.0))
        rotation.data.update_attribute("next_target")
        assert PORTALS.platform_at(rotation.data.next_target) == UPPER


def test_a_reached_target_is_followed_by_one_a_path_reaches() -> None:
    random.seed(2)
    rotation = _rotation(lambda: _fused(750.0, -400.0))
    for _ in range(20):
        rotation.data.next_target = (760.0, -400.0)  # within arrival of the feet
        rotation.data.update_attribute("next_target")
        assert rotation.data.next_target != (760.0, -400.0)
        assert PORTALS.platform_at(rotation.data.next_target) == UPPER
        assert rotation.data.next_feature == UPPER


def test_from_where_both_floors_are_reached_both_are_drawn() -> None:
    random.seed(3)
    rotation = _rotation(lambda: _fused(150.0, 0.0))
    drawn = set()
    for _ in range(40):
        rotation.data.next_target = (160.0, 0.0)
        rotation.data.update_attribute("next_target")
        drawn.add(PORTALS.platform_at(rotation.data.next_target))

    assert drawn == {LOWER, UPPER}


def test_arrival_is_ten_minimap_px_in_virtual_px() -> None:
    assert NextTargetMixin.BASE_ROTATION_THRESHOLD == 10 * 16
    assert NextTargetMixin.SMART_ROTATION_THRESHOLD == 4 * 16


def test_abandon_draws_only_where_a_path_reaches() -> None:
    random.seed(4)
    rotation = _rotation(lambda: _fused(750.0, -400.0))

    targets = [rotation._abandon_current_target() for _ in range(20)]

    assert {PORTALS.platform_at(t) for t in targets} == {UPPER}


def test_no_position_is_read_on_a_map_with_no_minimap() -> None:
    """A read there could only fail into the minimap's error handler."""
    reads: list[int] = []
    data = _data(PORTALS, lambda: reads.append(1) or _fused(0.0, 0.0))
    reads.clear()
    data.set_static("world_map", WorldMap(**{**_fields(PORTALS), "minimap": None}))

    reading = read_position(data)

    assert reading.value is None
    assert reads == []


def _fields(world: WorldMap) -> dict[str, object]:
    return {name: getattr(world, name) for name in world.__dataclass_fields__}


# --- the mob-spawn check -------------------------------------------------------


def test_the_mob_spawn_check_wanders_the_platforms_while_no_mob_shows() -> None:
    """
    No feature cycle on a `game_data` map: it heads for random points on the
    platforms, a new one each time one is reached.
    """
    data = _data(PORTALS, lambda: _fused(150.0, 0.0))
    owner = _Rotation(data)
    owner._create_rotation_attributes()
    data.set_feature("has_rotation_attributes")
    check = object.__new__(CheckMobsStillSpawn)
    check.data = data

    async def accepted(*args: object, **kwargs: object) -> None:
        return None

    check._validate_request_async = accepted  # pyright: ignore[reportAttributeAccessIssue]
    check._disable_decision_makers = lambda *names, **kwargs: None  # pyright: ignore[reportAttributeAccessIssue]
    check._toggle_chat_request = lambda: None  # pyright: ignore[reportAttributeAccessIssue]
    emitted: list[str] = []
    check.emit = lambda event_type, payload=None: emitted.append(event_type)  # pyright: ignore[reportAttributeAccessIssue]

    asyncio.run(check._setup_failsafe_procedure())

    update = data._managed["next_target"].update_function  # pyright: ignore[reportPrivateUsage]
    assert update.__func__ is NextTargetMixin._update_next_random_target  # pyright: ignore[reportFunctionMemberAccess]
    data.next_target = (150.0, 0.0)
    data.update_attribute("next_target")
    assert data.next_target != (150.0, 0.0)
    assert PORTALS.platform_at(data.next_target) is not None
    assert emitted == [MOVEMENT_TARGET_REACHED]


# --- the ladder check before a cast ------------------------------------------


@pytest.mark.parametrize(
    ("x", "y", "on_ladder"),
    [
        (300.0, -100.0, True),  # on `rope_grab`'s left rope
        (300.0, 0.0, False),  # on the floor under it
        (100.0, 0.0, False),
    ],
)
def test_no_skill_is_cast_on_a_rope_of_the_map(
    x: float, y: float, on_ladder: bool
) -> None:
    hitting = object.__new__(MobsHitting)
    hitting.data = _data(WorldMap.from_map_data(rope_grab()), lambda: _fused(x, y))

    assert hitting._currently_on_ladder() is on_ladder


def test_an_unsure_position_is_not_on_a_ladder() -> None:
    hitting = object.__new__(MobsHitting)
    unsure = Reading.unsure(0.0, "two characters")
    hitting.data = _data(WorldMap.from_map_data(rope_grab()), lambda: unsure)

    assert hitting._currently_on_ladder() is False


def test_the_ladder_check_reads_no_position() -> None:
    """The rotation reads it every cycle; a cast need not pay a camera match."""
    reads: list[int] = []
    data = _data(
        WorldMap.from_map_data(rope_grab()),
        lambda: reads.append(1) or _fused(300.0, -100.0),
    )
    data.reconfigure_attribute("current_position", threshold=1e-9)
    reads.clear()
    hitting = object.__new__(MobsHitting)
    hitting.data = data

    assert hitting._currently_on_ladder() is True
    assert reads == []
