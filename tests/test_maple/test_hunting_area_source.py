"""
The `hunting_area` destination source (#579, #571 spec section 7): where a cast
fires inside the Hunting Area, else the cell seen least
recently, and away from players who have settled.

Faked at the BotData level, with the mobs' detection stubbed: no game client.
The Provider is built as assembly builds it (`serving.destination`), with the
area's keys and `ATTACKS` as stand-ins. The client is drawn 1:1 with its play
area, so a client px is a virtual px; the clock is the Bot's, and only moves
when a test moves it.
"""

import math
import random
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from botting.core import BotData, StartupRefused
from botting.screen import Frame, Reading
from maple.decision_makers.providers import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    DESTINATION,
    POSITION,
    AreaPresence,
    Attack,
    DestinationProvider,
)
from maple.decision_makers.providers.hunting_area import NEAR, NOBODY, free_share
from maple.decision_makers.providers.sources import hunting_area as module
from maple.decision_makers.providers.sources.hunting_area import (
    HuntingAreaSource,
    best_spot,
    fires,
    reaches,
)
from maple.model.characters.reach import Reach, armed
from maple.model.world import HuntingArea, MinimapTransform, Stretch
from maple.model.world.hunting_area import on_stretches
from maple.screen.position import Camera, PositionSource, VirtualPosition
from maple.telemetry_events import (
    MOVEMENT_TARGET_REACHED,
    ROTATION_DESTINATION_PICKED,
)
from tests.test_maple.serving import attack, destination, override
from tests.test_maple.test_hunting_area import fixture_map, platform
from tests.test_maple.test_reach import CATALOGUE, POWER_STRIKE, SLASH_BLAST, SWORD

type Point = tuple[float, float]

#: With a minimap, so that arrival is recorded.
WORLD = replace(fixture_map(), minimap=MinimapTransform((500, 1500), 4))
FLAT = platform(WORLD, 1)
HIGH = platform(WORLD, 20)
#: Holds the whole of the flat Platform at y 0, from x 0 to 1000, and of the one
#: at y -1000 above it: 7 cells each, their middles at x 71, 214, 357, 500, 643,
#: 786 and 929.
AREA = HuntingArea(0, -1100, 1000, 50, "both")
STRETCHES = AREA.stretches(WORLD)
CLIENT = (1000, 600)
#: Shows x 0 to 1000 and y -300 to 300: the flat Platform, not the high one.
LOW_VIEW = Camera(0, -300, 1.0, 2.0, CLIENT)
#: 100 virtual px each side of the feet, 100 above and 50 below; 2 mobs.
ATTACKS = (attack(2),)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Scene:
    """
    The character, the Camera, the mobs on screen and who is near, as the
    source's Provider reads them. Change them through its methods.
    """

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        here: Point | None = (500.0, 0.0),
        camera: Camera | None = LOW_VIEW,
        mobs: Sequence[Point] = (),
        attacks: tuple[Attack, ...] = ATTACKS,
    ) -> None:
        self.here = here
        self.camera = camera
        self.mobs = list(mobs)
        self.clock = Clock()
        self.looks = 0
        self.emitted: list[tuple[str, Any]] = []
        monkeypatch.setattr(
            DestinationProvider,
            "emit",
            lambda _, event_type, payload=None: self.emitted.append(
                (event_type, payload)
            ),
        )
        monkeypatch.setattr(module, "get_mobs_positions_in_img", self._detect)
        image = Frame(np.zeros((600, 1000, 3), np.uint8), CLIENT, 0.0, True, True)
        self.provider = destination(
            WORLD,
            self._position,
            data=BotData("T", clock=self.clock),
            frame=lambda: image,
            position_fusion=self,  # its `camera`
            handle=1,
            rotation="hunting_area",
            area=AREA,
            stretches=STRETCHES,
            presence=NOBODY,
            attacks=attacks,
        )
        source = self.provider.source
        assert isinstance(source, HuntingAreaSource)
        self.source = source

    # --- what the Provider reads ---

    def _position(self) -> Reading[VirtualPosition]:
        if self.here is None:
            return Reading.unsure(0.0, "not placed")
        return Reading.read(VirtualPosition(*self.here, PositionSource.FUSED), 0.0)

    def _detect(self, *args: object, **kwargs: object) -> list[tuple[int, ...]]:
        """The mobs on screen, as boxes on the client, through the Camera."""
        self.looks += 1
        camera = self.camera
        assert camera is not None, "no look finds mobs without a Camera"
        return [
            (
                round(x - camera.x) - 5,
                round(y - camera.y) - 20,
                round(x - camera.x) + 5,
                round(y - camera.y),
            )
            for x, y in self.mobs
        ]

    # --- changing it ---

    def move(self, here: Point | None) -> None:
        self.here = here
        override(self.provider.data, POSITION, value=self._position())

    def settle(self, *others: Point, settled: bool = True) -> None:
        stretches = self.provider.data.read(AREA_STRETCHES)
        assert stretches is not None
        presence = AreaPresence(
            settled=settled,
            others=others,
            free_share=free_share(stretches, others) if settled else 1.0,
            inside=len(others),
        )
        override(self.provider.data, AREA_PRESENCE, value=presence)

    def presence(self, presence: AreaPresence) -> None:
        override(self.provider.data, AREA_PRESENCE, value=presence)

    def keep_to(self, stretches: tuple[Stretch, ...]) -> None:
        override(self.provider.data, AREA_STRETCHES, value=stretches)

    # --- asking it ---

    def next(self) -> Point:
        """`DESTINATION` refreshed, as `Rotation` refreshes it."""
        return self.provider.data.refresh(DESTINATION)

    def picked(self) -> list[dict[str, Any]]:
        return [p for t, p in self.emitted if t == ROTATION_DESTINATION_PICKED]

    def arrivals(self) -> int:
        return sum(1 for t, _ in self.emitted if t == MOVEMENT_TARGET_REACHED)


@pytest.fixture
def scene(monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401 - a factory
    return lambda **given: Scene(monkeypatch, **given)


# --- the registry, and what it refuses ----------------------------------------------


def test_it_is_built_for_the_hunting_area_rotation(scene: Any) -> None:  # noqa: ANN401
    assert isinstance(scene().provider.source, HuntingAreaSource)


def test_with_no_attacks_it_refuses_the_start() -> None:
    with pytest.raises(StartupRefused, match="attacks"):
        destination(
            WORLD,
            lambda: Reading.unsure(0.0, ""),
            rotation="hunting_area",
            area=AREA,
            stretches=STRETCHES,
            presence=NOBODY,
        )


def test_its_constants_start_where_the_spec_says() -> None:
    assert (HuntingAreaSource.ARRIVAL, HuntingAreaSource.LOOK_EVERY) == (64, 0.75)


# --- which spot ----------------------------------------------------------------------


def test_it_picks_the_spot_whose_attack_reaches_the_most_mobs(scene: Any) -> None:  # noqa: ANN401
    three = [(200.0, 0.0), (220.0, 0.0), (240.0, 0.0)]
    two = [(800.0, 0.0), (820.0, 0.0)]

    found = scene(mobs=three + two)

    # From 200, 220 or 240 a cast reaches the three: 240 is the nearest to 500.
    assert found.next() == (240.0, 0.0)
    assert found.picked() == [{"x": 240.0, "y": 0.0, "why": "mobs", "mobs": 3}]


def test_of_two_spots_reaching_as_many_it_picks_the_nearest(scene: Any) -> None:  # noqa: ANN401
    found = scene(
        here=(600.0, 0.0), mobs=[(200.0, 0.0), (210.0, 0.0), (750.0, 0.0), (760.0, 0.0)]
    )

    assert found.next() == (750.0, 0.0)


def test_mobs_outside_the_rectangle_are_not_counted(scene: Any) -> None:  # noqa: ANN401
    # Beside the area, on no stretch: the nearest spot to them is its edge, and
    # they are not counted from there.
    found = scene(here=(900.0, 0.0), mobs=[(1050.0, 0.0), (1060.0, 0.0)])

    assert found.next()[0] != 1000.0
    assert found.picked()[0]["why"] == "look_around"


def test_with_no_attack_firing_anywhere_it_looks_around(scene: Any) -> None:  # noqa: ANN401
    # One mob on each side: no spot reaches two.
    found = scene(mobs=[(200.0, 0.0), (800.0, 0.0)])

    # The flat Platform is on screen, so its cells are seen; the high one's
    # are not, and its middle cell is the nearest to the character.
    assert found.next() == (500.0, -1000.0)
    assert found.picked() == [
        {"x": 500.0, "y": -1000.0, "why": "look_around", "mobs": 0}
    ]


def test_looking_around_takes_the_cell_seen_least_recently_the_nearest_on_a_tie(
    scene: Any,  # noqa: ANN401
) -> None:
    def view(x: float, y: float, width: int = 1000) -> Camera:
        return Camera(round(x), round(y), 1.0, 2.0, (width, 600))

    # Nothing seen: the nearest cell, on the flat Platform.
    found = scene(here=(0.0, -400.0), camera=None)
    assert found.next() == pytest.approx((71.4, 0.0), abs=0.1)
    # On its way there, it sees the flat cells from x 500 at 1 s, and the high
    # ones up to x 500 at 2 s.
    for now, camera in ((1.0, view(500, -300)), (2.0, view(-500, -1300))):
        found.clock.now = now
        found.camera = camera
        assert found.next() == pytest.approx((71.4, 0.0), abs=0.1)

    # At 3 s it arrives, and sees the cell it is in: of the cells never seen, the
    # nearest is the next flat one.
    found.clock.now = 3.0
    found.camera = view(-100, -300, width=300)
    found.move((71.4, 0.0))
    assert found.next() == pytest.approx((214.3, 0.0), abs=0.1)
    # At 4 s, there, it sees up to x 400: the high cells from 643 are left.
    found.clock.now = 4.0
    found.camera = view(100, -300, width=300)
    found.move((214.3, 0.0))
    assert found.next() == pytest.approx((642.9, -1000.0), abs=0.1)
    # At 5 s, there, it sees the high cells from 500: every cell is seen, and
    # the flat ones from 500, at 1 s, were the least recently, though the high
    # ones up to 357, at 2 s, are nearer.
    found.clock.now = 5.0
    found.camera = view(500, -1300)
    found.move((642.9, -1000.0))
    assert found.next() == pytest.approx((642.9, 0.0), abs=0.1)
    assert {p["why"] for p in found.picked()} == {"look_around"}


def test_a_cell_is_seen_when_its_middle_is_in_the_play_area_with_a_camera(
    scene: Any,  # noqa: ANN401
) -> None:
    # The flat Platform's cells up to x 500 on screen; the high one's not.
    found = scene(here=(100.0, 0.0), camera=replace(LOW_VIEW, x=-500))

    # Unseen: the flat cells from 643, and the high ones, farther.
    assert found.next() == pytest.approx((643, 0.0), abs=1)


def test_the_first_destination_before_anything_is_seen_is_the_nearest_cell(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene(here=(360.0, 0.0), camera=None)

    assert found.next() == pytest.approx((357.14, 0.0), abs=0.01)


# --- when it picks ------------------------------------------------------------------


def test_it_keeps_its_destination_until_arrival_then_stands_and_looks_every_0_75_s(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene(mobs=[(200.0, 0.0), (220.0, 0.0), (240.0, 0.0)])
    assert found.next() == (240.0, 0.0)
    assert found.looks == 1

    # On its way, 80 px off: kept, and no look.
    found.move((320.0, 0.0))
    assert found.next() == (240.0, 0.0)
    assert (found.looks, found.arrivals()) == (1, 0)

    # Within 64 px: arrived, recorded once, and a look; the spot still reaches
    # its three mobs, so the character stands there.
    found.move((250.0, 0.0))
    assert found.next() == (240.0, 0.0)
    assert (found.looks, found.arrivals()) == (2, 1)

    # Standing: a look at most every 0.75 s.
    found.clock.now = 0.5
    assert found.next() == (240.0, 0.0)
    assert found.looks == 2
    found.clock.now = 0.8
    assert found.next() == (240.0, 0.0)
    assert (found.looks, found.arrivals()) == (3, 1)
    assert len(found.picked()) == 1  # no refresh that kept it said anything

    # The mobs are gone at the next look: it picks again.
    found.mobs = []
    found.clock.now = 1.6
    after = found.next()
    assert after != (240.0, 0.0)
    assert found.looks == 4
    assert [p["why"] for p in found.picked()] == ["mobs", "look_around"]


def test_on_arrival_where_too_few_mobs_are_left_it_picks_again(scene: Any) -> None:  # noqa: ANN401
    found = scene(mobs=[(200.0, 0.0), (220.0, 0.0)])
    assert found.next() == (220.0, 0.0)

    found.mobs = [(220.0, 0.0)]
    found.move((220.0, 0.0))

    assert found.next() != (220.0, 0.0)
    assert found.arrivals() == 1


def test_a_mob_is_reached_by_one_client_px_at_the_frames_scale(
    scene: Any,  # noqa: ANN401
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def pick(right_mob_left: int) -> str:
        """
        Why the first pick is made, on a play area half the client's: 2 client
        px per virtual px, so one client px of overlap is half a virtual px.
        Client x 0 is virtual 0, and client y 300 is virtual 0.

        One mob stands at virtual 200 (195 to 205), and one's box starts at
        client `right_mob_left`. The fixture attack, 2 mobs, reaches 100
        virtual px from the feet: from 200, to virtual 300, client 600.
        """
        found = scene(camera=Camera(0, -150, 1.0, 2.0, (500, 300)))
        boxes = [(390, 260, 410, 300), (right_mob_left, 260, right_mob_left + 40, 300)]
        monkeypatch.setattr(module, "get_mobs_positions_in_img", lambda *_: boxes)
        found.next()
        return found.picked()[-1]["why"]

    # Client 599: one client px, half a virtual px, of overlap. Both are
    # reached from 200, and the attack fires there.
    assert pick(599) == "mobs"
    # Client 600: touching, no overlap. Nothing fires.
    assert pick(600) == "look_around"


# --- with no Camera ------------------------------------------------------------------


def test_with_no_camera_an_allowed_destination_is_kept_and_a_pick_looks_around(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene(mobs=[(200.0, 0.0), (220.0, 0.0), (240.0, 0.0)])
    assert found.next() == (240.0, 0.0)

    found.camera = None
    found.move((400.0, 0.0))
    assert found.next() == (240.0, 0.0)

    # Arrived, the look sees no mob: a look-around, though the mobs are there.
    found.move((240.0, 0.0))
    found.next()
    assert found.looks == 1
    assert found.picked()[-1]["why"] == "look_around"
    assert found.picked()[-1]["mobs"] == 0


# --- other players ---------------------------------------------------------------------


def test_once_settled_mobs_near_a_settled_player_are_not_counted(
    scene: Any,  # noqa: ANN401
) -> None:
    near = [(200.0, 0.0), (220.0, 0.0), (240.0, 0.0)]
    far = [(800.0, 0.0), (820.0, 0.0)]
    before = scene(mobs=near + far)
    before.settle((150.0, 0.0), settled=False)
    after = scene(mobs=near + far)
    after.settle((150.0, 0.0))

    # Before settled, the three near them are counted; after, only the two.
    assert before.next() == (240.0, 0.0)
    assert after.next() == (800.0, 0.0)
    assert after.picked()[-1]["mobs"] == 2


def test_a_destination_within_near_of_a_settled_player_is_replaced_at_once(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene(mobs=[(200.0, 0.0), (220.0, 0.0), (240.0, 0.0)])
    assert found.next() == (240.0, 0.0)

    found.settle((150.0, 0.0))

    replaced = found.next()
    assert math.dist(replaced, (150.0, 0.0)) > NEAR
    assert on_stretches(replaced, STRETCHES)


def test_once_settled_no_cell_to_look_at_lies_near_a_settled_player(
    scene: Any,  # noqa: ANN401
) -> None:
    # Nothing on screen, the high Platform's cells far from the player.
    found = scene(here=(100.0, 0.0), camera=None)
    found.keep_to(STRETCHES[:1])
    found.settle((150.0, 0.0))

    # Within 350 of 150, the cells up to 500 are not looked at.
    assert found.next() == pytest.approx((643, 0.0), abs=1)


# --- crowded out ------------------------------------------------------------------------


def test_crowded_out_it_stays_at_the_last_sure_position_and_says_so_once(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene(mobs=[(800.0, 0.0), (820.0, 0.0)])
    found.next()
    found.move((520.0, 0.0))
    found.next()

    found.presence(
        AreaPresence(settled=True, others=((900.0, 0.0),), free_share=0.0, inside=1)
    )
    assert found.next() == (520.0, 0.0)
    found.move(None)
    assert found.next() == (520.0, 0.0)
    assert found.source.abandon() == (520.0, 0.0)
    assert found.next() == (520.0, 0.0)

    whys = [p["why"] for p in found.picked()]
    assert whys == ["mobs", "crowded_out"]
    assert found.picked()[-1] == {"x": 520.0, "y": 0.0, "why": "crowded_out", "mobs": 0}

    # Room again: it picks at once.
    found.move((520.0, 0.0))
    found.presence(NOBODY)
    assert found.next() == (800.0, 0.0)


# --- Abandon ------------------------------------------------------------------------------


def test_abandon_gives_random_points_on_the_stretches_away_from_settled_players(
    scene: Any,  # noqa: ANN401
) -> None:
    found = scene()
    found.source.rng = random.Random(7)
    found.next()
    before = [found.provider.abandon() for _ in range(100)]
    found.settle((150.0, 0.0), (300.0, -1000.0))
    after = [found.provider.abandon() for _ in range(300)]

    assert all(p is not None and on_stretches(p, STRETCHES) for p in before + after)
    assert any(p is not None and math.dist(p, (150.0, 0.0)) <= NEAR for p in before)
    others = ((150.0, 0.0), (300.0, -1000.0))
    assert all(
        p is not None and all(math.dist(p, o) > NEAR for o in others) for p in after
    )
    assert found.picked()[-1]["why"] == "abandon"


# --- a long run --------------------------------------------------------------------------


def test_over_a_long_run_every_destination_is_on_a_stretch_unless_crowded_out(
    scene: Any,  # noqa: ANN401
) -> None:
    """
    Random mobs, in the area and beside it, random positions and Cameras, players
    settling and leaving, reachability changing and Abandons: every destination
    is on a stretch of `AREA_STRETCHES`, and once settled none is within `NEAR`
    of another player, except while crowded out.
    """
    rng = random.Random(579)
    found = scene()
    found.source.rng = random.Random(5790)
    crowded = 0
    for step in range(1500):
        found.clock.now = step * 0.3
        if rng.random() < 0.1:
            found.keep_to(rng.choice([STRETCHES, STRETCHES[:1], STRETCHES[1:]]))
        if rng.random() < 0.1:
            others = tuple(
                (rng.uniform(-300, 1300), rng.choice([0.0, -1000.0]))
                for _ in range(rng.randint(0, 4))
            )
            found.settle(*others, settled=rng.random() < 0.6)
        found.camera = (
            None
            if rng.random() < 0.2
            else Camera(
                rng.randint(-600, 600), rng.randint(-1400, -200), 1.0, 2.0, CLIENT
            )
        )
        found.mobs = [
            (rng.uniform(-200, 1200), rng.choice([0.0, -1000.0, -500.0]))
            for _ in range(rng.randint(0, 8))
        ]
        if rng.random() < 0.05:
            found.provider.abandon()
            got = found.provider.data.read(DESTINATION)
        else:
            got = found.next()
        # Wherever it heads, the character goes most of the way, or is lost.
        roll = rng.random()
        if roll < 0.1:
            found.move(None)
        elif roll < 0.7:
            found.move((got[0] + rng.uniform(-60, 60), got[1]))
        else:
            found.move((rng.uniform(0, 1000), rng.choice([0.0, -1000.0])))

        stretches = found.provider.data.read(AREA_STRETCHES)
        presence = found.provider.data.read(AREA_PRESENCE)
        assert stretches is not None
        assert presence is not None
        if found.source._crowded:  # pyright: ignore[reportPrivateUsage] - the exception
            crowded += 1
            continue
        assert on_stretches(got, stretches), (step, got)
        if presence.settled:
            assert all(math.dist(got, o) > NEAR for o in presence.others), (step, got)
    picked = {p["why"] for p in found.picked()}
    assert picked == {"mobs", "look_around", "abandon", "crowded_out"}
    assert 0 < crowded < 1500


# --- the plain functions -------------------------------------------------------------------


#: Virtual px are client px: one client px of overlap is one virtual px.
ONE = (1.0, 1.0)


def box(x: float, y: float = 0.0, half: float = 30.0, height: float = 40.0) -> Any:  # noqa: ANN401
    """A mob's box in virtual px, standing at `x`, `y`: `half` each side, `height` tall."""
    return (x - half, y - height, x + half, y)


#: Power Strike's and Slash Blast's reach with a one-handed sword: 22 to 73 px in
#: front of the feet, a 14 px band at chest height, one-sided.
POWER_STRIKE_1 = replace(attack(1), armed=armed(POWER_STRIKE, SWORD, CATALOGUE))
SLASH_BLAST_3 = replace(attack(3), armed=armed(SLASH_BLAST, SWORD, CATALOGUE))
SWORDSMAN = (SLASH_BLAST_3, POWER_STRIKE_1)


def test_a_cast_reaches_the_mobs_whose_box_overlaps_its_box_from_the_feet() -> None:
    reach = Reach(-100, -100, 100, 50)
    inside = [box(100.0, half=5.0), box(-100.0, half=5.0), box(0.0, -100.0 + 20.0)]
    outside = [box(106.0, half=5.0), box(-106.0, half=5.0), box(0.0, 50.0 + 100.0)]

    assert reaches((0.0, 0.0), inside + outside, reach, scale=ONE) == 3


def test_with_every_mobs_feet_at_the_spots_height_a_box_spanning_the_chest_band_is_reached() -> (
    None
):
    reach = armed(POWER_STRIKE, SWORD, CATALOGUE).reach
    # Its feet at the spot's y, 0; the band is 16 to 30 px above them. A point at
    # the feet reaches nothing, and the box does.
    assert reach.lt_y < 0
    assert reach.rb_y < 0
    assert reaches((0.0, 0.0), [box(-50.0)], reach, scale=ONE) == 1
    assert reaches((0.0, 0.0), [box(-50.0, height=5.0)], reach, scale=ONE) == 0


def test_a_one_sided_reach_counts_the_mobs_of_the_larger_side() -> None:
    reach = armed(POWER_STRIKE, SWORD, CATALOGUE).reach

    left = [box(-50.0)]
    right = [box(50.0), box(60.0)]

    assert reaches((0.0, 0.0), left, reach, scale=ONE) == 1
    assert reaches((0.0, 0.0), right, reach, scale=ONE) == 2
    # One on one side and two on the other: not summed.
    assert reaches((0.0, 0.0), left + right, reach, scale=ONE) == 2


def test_an_attack_fires_where_it_reaches_its_min_mobs() -> None:
    mobs = [box(300.0), box(330.0), box(360.0)]

    assert fires((300.0, 0.0), mobs, SWORDSMAN, scale=ONE) == (0, 3)
    assert fires((300.0, 0.0), mobs[:2], SWORDSMAN, scale=ONE) == (1, 2)
    assert fires((0.0, 0.0), mobs, SWORDSMAN, scale=ONE) is None


def test_the_best_spot_is_on_a_stretch_nearest_a_mob() -> None:
    flat = STRETCHES[0]
    assert flat.platform is FLAT

    # A mob beside the stretch's end: the spot is the end.
    found = best_spot((flat,), [box(1050.0)], (attack(1),), here=None, scale=ONE)

    assert found == ((1000.0, 0.0), 1)
    assert best_spot((flat,), [], (attack(1),), here=None, scale=ONE) is None
    assert HIGH in {s.platform for s in STRETCHES}


def test_the_best_spot_prefers_where_slash_blast_fires_over_where_only_power_strike_does() -> (
    None
):
    flat = STRETCHES[0]
    group = [box(300.0), box(330.0), box(360.0)]
    lone = [box(600.0)]

    # The lone mob's spot is the nearest to the character, and a mob there is
    # reached by Power Strike alone.
    found = best_spot((flat,), group + lone, SWORDSMAN, here=(620.0, 0.0), scale=ONE)

    # From 300 or 360 a cast reaches all three: 360 is the nearer to 620.
    assert found == ((360.0, 0.0), 3)


def test_the_best_spot_still_picks_a_lone_mob_when_no_group_exists() -> None:
    flat = STRETCHES[0]

    found = best_spot((flat,), [box(600.0)], SWORDSMAN, here=(100.0, 0.0), scale=ONE)

    assert found == ((600.0, 0.0), 1)


def test_a_spot_no_attack_fires_at_is_not_picked() -> None:
    flat = STRETCHES[0]

    assert best_spot((flat,), [box(600.0)], (attack(2),), here=None, scale=ONE) is None


def test_of_two_spots_where_the_same_attack_fires_the_one_reaching_more_wins() -> None:
    flat = STRETCHES[0]
    # Power Strike only: 2 mobs reached at 300, 1 at 600.
    mobs = [box(300.0), box(330.0), box(600.0)]

    found = best_spot((flat,), mobs, (POWER_STRIKE_1,), here=(620.0, 0.0), scale=ONE)

    assert found is not None
    assert found[1] == 2
