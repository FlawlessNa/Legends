"""
`VRPhysics`: movement in virtual px, from `Physics.img`, the character's
multipliers and the Calibration constants.
"""

import math
from pathlib import Path
from typing import Self

import pytest

from maple.model.mechanics import physics as physics_module
from maple.model.mechanics.physics import (
    CLIMB_SPEED,
    TELEPORT_REACH,
    Calibration,
    VRPhysics,
)

# Not the client's values, so a test can't pass by reading a hard-coded table.
GAME_FILES = {
    "walkSpeed": 100.0,
    "jumpSpeed": 600.0,
    "gravityAcc": 2400.0,
    "fallSpeed": 700.0,
    "walkForce": 140000.0,
    "walkDrag": 60000.0,
}


def _physics(**kwargs: object) -> VRPhysics:
    return VRPhysics.from_game_files(GAME_FILES, **kwargs)  # pyright: ignore[reportArgumentType]


# --- at multiplier 1.0 -----------------------------------------------------------


def test_the_values_come_from_the_game_files() -> None:
    vr = _physics()

    assert vr.walk_speed == 100.0
    assert vr.jump_speed == 600.0
    assert vr.gravity == 2400.0
    assert vr.fall_speed == 700.0


def test_climb_and_teleport_start_from_their_named_constants() -> None:
    vr = _physics()

    assert vr.climb_speed == CLIMB_SPEED == 125.0
    assert vr.teleport_reach == TELEPORT_REACH == 150.0


def test_the_jump_arc_follows_the_formulas() -> None:
    vr = _physics()

    assert vr.jump_height == pytest.approx(600.0**2 / (2 * 2400.0))  # 75
    assert vr.jump_duration == pytest.approx(2 * 600.0 / 2400.0)  # 0.5 s
    assert vr.jump_reach() == pytest.approx(0.5 * 100.0)
    assert vr.jump_reach(speed=40.0) == pytest.approx(0.5 * 40.0)


def test_a_jump_lands_lower_later_and_higher_sooner() -> None:
    vr = _physics()

    # From the top (75 px up), 75 + 25 px down at most 700 px/s: still free fall.
    assert vr.jump_landing_time(25.0) == pytest.approx(0.25 + math.sqrt(2 * 100 / 2400))
    assert vr.jump_landing_time(-75.0) == pytest.approx(0.25)
    assert vr.jump_reach(drop=25.0) == pytest.approx(100.0 * vr.jump_landing_time(25.0))
    with pytest.raises(ValueError, match="rises 75.0"):
        vr.jump_landing_time(-76.0)


def test_a_long_fall_is_capped_at_the_fall_speed() -> None:
    vr = _physics()
    to_full_speed = 700.0**2 / (2 * 2400.0)

    assert vr.fall_time(to_full_speed) == pytest.approx(700.0 / 2400.0)
    assert vr.fall_time(to_full_speed + 350.0) == pytest.approx(700.0 / 2400.0 + 0.5)
    with pytest.raises(ValueError, match="negative"):
        vr.fall_time(-1.0)


def test_a_missing_game_file_value_is_named() -> None:
    with pytest.raises(KeyError, match="jumpSpeed, fallSpeed"):
        VRPhysics.from_game_files({"walkSpeed": 125.0, "gravityAcc": 2000.0})


# --- the walk's start and stop (#503) -------------------------------------------


def test_the_walks_acceleration_and_slide_are_its_forces_over_the_mass() -> None:
    vr = _physics()

    assert vr.walk_acceleration == pytest.approx(140000.0 / 100)  # 1400 px/s²
    assert vr.walk_deceleration == pytest.approx(60000.0 / 100)  # 600 px/s²
    assert vr.stop_slide == pytest.approx(100.0**2 / (2 * 600.0))


def test_a_faster_character_slides_further_on_the_same_drag() -> None:
    base, fast = _physics(), _physics(speed_multiplier=1.4)

    assert fast.walk_deceleration == base.walk_deceleration
    assert fast.stop_slide == pytest.approx(1.4**2 * base.stop_slide)


def test_a_moving_walk_releases_its_slide_early() -> None:
    vr = _physics()

    # Walking at 100 px/s, the key held T s then a slide: 100 T + slide = 60.
    assert vr.walk_press_time(60.0, moving=True) == pytest.approx(
        (60.0 - vr.stop_slide) / 100.0
    )
    # Nearer than the slide: released at once, never a negative hold.
    assert vr.walk_press_time(vr.stop_slide / 2, moving=True) == 0.0
    assert vr.walk_press_time(-5.0, moving=True) == 0.0


def test_a_walk_from_rest_pays_for_its_acceleration() -> None:
    vr = _physics()
    ramp = 100.0**2 / (2 * 1400.0)

    assert vr.walk_press_time(60.0, moving=False) == pytest.approx(
        (60.0 + ramp - vr.stop_slide) / 100.0
    )


def test_a_walk_too_short_to_reach_full_speed_slides_from_the_speed_it_reached() -> (
    None
):
    vr = _physics()
    held = vr.walk_press_time(5.0, moving=False)
    reached = 1400.0 * held

    assert reached < vr.walk_speed
    assert 0.5 * 1400.0 * held**2 + reached**2 / (2 * 600.0) == pytest.approx(5.0)


def test_with_no_acceleration_or_slide_a_walk_lasts_its_length() -> None:
    vr = VRPhysics(100.0, 600.0, 2400.0, 700.0, 125.0, 150.0)

    assert vr.walk_press_time(60.0, moving=False) == pytest.approx(0.6)
    assert vr.walk_press_time(60.0, moving=True) == pytest.approx(0.6)


# --- multipliers -----------------------------------------------------------------


def test_the_speed_multiplier_scales_walk_climb_and_reach_linearly() -> None:
    base, fast = _physics(), _physics(speed_multiplier=1.4)

    assert fast.walk_speed == pytest.approx(1.4 * base.walk_speed)
    assert fast.climb_speed == pytest.approx(1.4 * base.climb_speed)
    assert fast.jump_reach() == pytest.approx(1.4 * base.jump_reach())
    assert fast.jump_height == base.jump_height
    assert fast.teleport_reach == base.teleport_reach


def test_the_jump_multiplier_scales_the_take_off_speed_linearly() -> None:
    base, high = _physics(), _physics(jump_multiplier=1.1)

    assert high.jump_speed == pytest.approx(1.1 * base.jump_speed)
    # The arc follows from the take-off speed: the height goes with its square,
    # the time in the air and the reach with it.
    assert high.jump_height == pytest.approx(1.1**2 * base.jump_height)
    assert high.jump_duration == pytest.approx(1.1 * base.jump_duration)
    assert high.jump_reach() == pytest.approx(1.1 * base.jump_reach())
    assert high.walk_speed == base.walk_speed


def test_the_multipliers_compose() -> None:
    vr = _physics(speed_multiplier=1.4, jump_multiplier=1.1)

    assert vr.jump_reach() == pytest.approx(1.4 * 1.1 * _physics().jump_reach())


# --- Calibration constants -------------------------------------------------------


@pytest.mark.parametrize(
    ("constant", "field"),
    [
        ("walk", "walk_speed"),
        ("jump", "jump_speed"),
        ("climb", "climb_speed"),
        ("teleport", "teleport_reach"),
    ],
)
def test_each_constant_multiplies_its_derivation_and_nothing_else(
    constant: str, field: str
) -> None:
    base = _physics(speed_multiplier=1.4, jump_multiplier=1.1)
    calibrated = _physics(
        speed_multiplier=1.4,
        jump_multiplier=1.1,
        calibration=Calibration(**{constant: 0.8}),
    )

    for name in ("walk_speed", "jump_speed", "climb_speed", "teleport_reach"):
        expected = getattr(base, name) * (0.8 if name == field else 1.0)
        assert getattr(calibrated, name) == pytest.approx(expected)
    assert calibrated.gravity == base.gravity
    assert calibrated.fall_speed == base.fall_speed


def test_a_constant_is_a_multiplier_not_a_distance() -> None:
    # The same constant scales the walk by the same share whatever it derives from.
    constants = Calibration(walk=1.5)

    for multiplier in (1.0, 1.2, 1.4):
        base = _physics(speed_multiplier=multiplier)
        calibrated = _physics(speed_multiplier=multiplier, calibration=constants)
        assert calibrated.walk_speed / base.walk_speed == pytest.approx(1.5)
        assert calibrated.jump_reach() / base.jump_reach() == pytest.approx(1.5)


def test_the_calibration_mapping_defaults_each_constant_to_one() -> None:
    assert Calibration.from_mapping(None) == Calibration(1.0, 1.0, 1.0, 1.0)
    assert Calibration.from_mapping({"jump": 1.05, "teleport": 1}) == Calibration(
        jump=1.05, teleport=1.0
    )


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"speed": 1.1}, "no constant 'speed'; the constants are walk, jump"),
        ({"walk": 0}, r"`calibration.walk` must be a positive number"),
        ({"jump": -1.0}, r"`calibration.jump` must be a positive number"),
        ({"climb": "1.1"}, r"`calibration.climb` must be a positive number"),
        ({"teleport": True}, r"`calibration.teleport` must be a positive number"),
        ({"walk": math.inf}, r"`calibration.walk` must be a positive number"),
    ],
)
def test_a_bad_calibration_mapping_is_refused(
    mapping: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Calibration.from_mapping(mapping)


# --- from the catalogue ----------------------------------------------------------


def test_load_reads_the_latest_catalogues_physics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    roots: list[Path] = []

    class _Catalogue:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def physics(self) -> dict[str, float]:
            return GAME_FILES

    def _latest(root: Path) -> _Catalogue:
        roots.append(root)
        return _Catalogue()

    monkeypatch.setattr(physics_module.Catalogue, "latest", _latest)

    vr = VRPhysics.load(
        speed_multiplier=1.4, calibration=Calibration(jump=0.9), root=tmp_path
    )

    assert roots == [tmp_path]
    assert vr == _physics(speed_multiplier=1.4, calibration=Calibration(jump=0.9))
