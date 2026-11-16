"""
Movement physics.

`VRPhysics` is the character's movement in virtual px (`CONTEXT.md` ->
Virtual coordinates): walk speed, climb speed, jump arc and teleport reach.
Walk and jump come from the game files (`Map/Physics.img`, through
`Catalogue.physics()`), times the character's speed and jump multipliers.
Climb and teleport are not in the game files, so they start from named
constants until Trials measure them (`configs/trials/physics.json`, #397). Each value is then multiplied by
its Calibration constant (`Calibration`).

Movement Plans are planned and compiled on it (#396), with the character's
current speed and jump multipliers: a bot reads `Physics.img` once
(`game_physics`) and builds a `VRPhysics` from it whenever it plans, so a
change of stat reaches the next Path.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from game_data.catalogue import Catalogue
from game_data.config import STORE

#: Virtual px one teleport moves the character. Not in `Physics.img`: it
#: starts from the old minimap physics' `TELEPORT_DISTANCE` (150), until the
#: physics Trial schedule measures it (#397).
TELEPORT_REACH = 150.0

#: Virtual px/s the character climbs a rope or ladder at. Not in
#: `Physics.img`: `compile_movements` times climbs at the walk speed today
#: (`walkSpeed`, 125), so it starts there, until the physics Trial schedule
#: measures it (#397).
CLIMB_SPEED = 125.0

#: The character's mass, by which the client divides `Physics.img`'s forces
#: (`walkForce`, `walkDrag`) into accelerations. The game's own value, not a
#: tuning constant: 100 when nothing (shoes, a mount) changes it. Trial records
#: agree (#503): walks started from rest travel their timed length plus about 3
#: virtual px, against 6 derived from these accelerations.
CHARACTER_MASS = 100.0

#: The `Physics.img` keys `VRPhysics` reads.
PHYSICS_KEYS = (
    "walkSpeed",
    "jumpSpeed",
    "gravityAcc",
    "fallSpeed",
    "walkForce",
    "walkDrag",
)

#: The Calibration constants a profile's `calibration` setting may name.
CALIBRATION_KEYS = ("walk", "jump", "climb", "teleport")


def game_physics(root: Path = STORE) -> dict[str, float]:
    """
    The latest extraction's `Map/Physics.img` values, as
    `VRPhysics.from_game_files` takes them.

    :raises CatalogueError: The store has no extraction.
    """
    with Catalogue.latest(root) as cat:
        return dict(cat.physics())


@dataclass(frozen=True, slots=True)
class Calibration:
    """
    The Calibration constants (`CONTEXT.md`): each multiplies one derivation,
    and is never an absolute distance. 1.0 leaves the derivation as it is.

    :ivar walk: Multiplies the walk speed, and so the jump's horizontal reach.
    :ivar jump: Multiplies the jump's take-off speed, as the jump multiplier
        does.
    :ivar climb: Multiplies the climb speed.
    :ivar teleport: Multiplies the teleport reach.
    """

    walk: float = 1.0
    jump: float = 1.0
    climb: float = 1.0
    teleport: float = 1.0

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object] | None) -> Calibration:
        """
        The constants a profile's `calibration` setting names; any it leaves
        out are 1.0.

        :raises ValueError: A key that names no constant, or a value that is
            not a positive, finite number.
        """
        if mapping is None:
            return cls()
        unknown = sorted(str(key) for key in mapping if key not in CALIBRATION_KEYS)
        if unknown:
            raise ValueError(
                f"`calibration` has no constant {', '.join(map(repr, unknown))}; "
                f"the constants are {', '.join(CALIBRATION_KEYS)}"
            )
        values: dict[str, float] = {}
        for key, value in mapping.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not 0 < value < math.inf
            ):
                raise ValueError(
                    f"`calibration.{key}` must be a positive number, not {value!r}"
                )
            values[key] = float(value)
        return cls(**values)


@dataclass(frozen=True, slots=True)
class VRPhysics:
    """
    The character's movement, in virtual px and seconds. Build it with
    `load` or `from_game_files`; the fields are the values after the
    multipliers and Calibration constants.

    Virtual y grows downwards; heights and drops here are distances.

    :ivar walk_speed: Virtual px/s on a platform, and sideways in the air.
    :ivar jump_speed: The jump's upward take-off speed, virtual px/s.
    :ivar gravity: Downward acceleration in the air, virtual px/s².
    :ivar fall_speed: The fastest the character falls, virtual px/s.
    :ivar climb_speed: Virtual px/s on a rope or ladder.
    :ivar teleport_reach: Virtual px one teleport moves the character.
    :ivar walk_acceleration: Virtual px/s² the character gains walking from rest,
        a direction key down: `walkForce ÷ CHARACTER_MASS`. Infinite (at full
        speed at once) when built by hand.
    :ivar walk_deceleration: Virtual px/s² the character loses once the direction
        key is up, sliding to a stop: `walkDrag ÷ CHARACTER_MASS`. Infinite (no
        slide) when built by hand.
    """

    walk_speed: float
    jump_speed: float
    gravity: float
    fall_speed: float
    climb_speed: float
    teleport_reach: float
    walk_acceleration: float = math.inf
    walk_deceleration: float = math.inf

    @classmethod
    def load(
        cls,
        *,
        speed_multiplier: float = 1.0,
        jump_multiplier: float = 1.0,
        calibration: Calibration | None = None,
        root: Path = STORE,
    ) -> VRPhysics:
        """
        The physics from the latest extraction's `Map/Physics.img`.

        :raises CatalogueError: The store has no extraction.
        :raises KeyError: `Physics.img` lacks a key `VRPhysics` reads.
        """
        return cls.from_game_files(
            game_physics(root),
            speed_multiplier=speed_multiplier,
            jump_multiplier=jump_multiplier,
            calibration=calibration,
        )

    @classmethod
    def from_game_files(
        cls,
        physics: Mapping[str, float],
        *,
        speed_multiplier: float = 1.0,
        jump_multiplier: float = 1.0,
        calibration: Calibration | None = None,
    ) -> VRPhysics:
        """
        The physics from `Physics.img`'s values, as `Catalogue.physics()`
        gives them.

        The walk speed is `walkSpeed × speed_multiplier × calibration.walk`,
        and the take-off speed `jumpSpeed × jump_multiplier × calibration.jump`.
        The climb speed takes the speed multiplier too, since climbs are timed
        like walks today; the teleport reach takes neither multiplier, as
        today. Gravity, the fall speed and the walk's acceleration and
        deceleration are the game's own (`CHARACTER_MASS`).

        :raises KeyError: `physics` lacks a key `VRPhysics` reads, named in
            the message.
        """
        missing = [key for key in PHYSICS_KEYS if key not in physics]
        if missing:
            raise KeyError(f"Physics.img has no {', '.join(missing)}")
        constants = calibration or Calibration()
        return cls(
            walk_speed=physics["walkSpeed"] * speed_multiplier * constants.walk,
            jump_speed=physics["jumpSpeed"] * jump_multiplier * constants.jump,
            gravity=physics["gravityAcc"],
            fall_speed=physics["fallSpeed"],
            climb_speed=CLIMB_SPEED * speed_multiplier * constants.climb,
            teleport_reach=TELEPORT_REACH * constants.teleport,
            walk_acceleration=physics["walkForce"] / CHARACTER_MASS,
            walk_deceleration=physics["walkDrag"] / CHARACTER_MASS,
        )

    @property
    def stop_slide(self) -> float:
        """
        Virtual px the character slides on, walking at `walk_speed`, after its
        direction key comes up: `walk_speed² ÷ 2 walk_deceleration`.
        """
        return walk_stop_slide(self.walk_speed, self.walk_deceleration)

    def walk_press_time(self, distance: float, *, moving: bool) -> float:
        """
        Seconds to hold the direction key so the character comes to rest
        `distance` virtual px ahead (`walk_press_time`).
        """
        return walk_press_time(
            distance,
            speed=self.walk_speed,
            acceleration=self.walk_acceleration,
            deceleration=self.walk_deceleration,
            moving=moving,
        )

    @property
    def jump_height(self) -> float:
        """How high the jump rises above its take-off: `jump_speed² ÷ 2g`."""
        return self.jump_speed**2 / (2 * self.gravity)

    @property
    def jump_duration(self) -> float:
        """Seconds from take-off to landing back at the take-off's height."""
        return self.jump_landing_time(0.0)

    def jump_landing_time(self, drop: float) -> float:
        """
        Seconds from take-off to landing `drop` virtual px below the take-off:
        the rise, `jump_speed ÷ g`, then the fall from the top. Landing above
        the take-off is a negative `drop`, down to `-jump_height`.

        :raises ValueError: `drop` is above the top of the jump.
        """
        if drop < -self.jump_height:
            raise ValueError(
                f"a jump rises {self.jump_height:.1f} virtual px; it can't land "
                f"{-drop:.1f} above its take-off"
            )
        return self.jump_speed / self.gravity + self.fall_time(self.jump_height + drop)

    def jump_reach(self, drop: float = 0.0, speed: float | None = None) -> float:
        """
        Virtual px the jump carries the character sideways before it lands
        `drop` below its take-off, moving at `speed` (the walk speed when not
        given).
        """
        sideways = self.walk_speed if speed is None else speed
        return sideways * self.jump_landing_time(drop)

    def fall_time(self, distance: float) -> float:
        """
        Seconds to fall `distance` virtual px from rest: under gravity until
        the character reaches `fall_speed`, then at that speed.

        :raises ValueError: `distance` is negative.
        """
        if distance < 0:
            raise ValueError(f"can't fall a negative distance, {distance}")
        to_full_speed = self.fall_speed**2 / (2 * self.gravity)
        if distance <= to_full_speed:
            return math.sqrt(2 * distance / self.gravity)
        return (
            self.fall_speed / self.gravity
            + (distance - to_full_speed) / self.fall_speed
        )


def walk_stop_slide(speed: float, deceleration: float) -> float:
    """Virtual px a character walking at `speed` slides on once its key is up."""
    return speed**2 / (2 * deceleration)


def walk_press_time(
    distance: float,
    *,
    speed: float,
    acceleration: float,
    deceleration: float,
    moving: bool,
) -> float:
    """
    Seconds to hold a direction key so the character comes to rest `distance`
    virtual px ahead, once the slide after the key comes up is counted (#503).

    `moving`: the character already walks that way at `speed` when the key's
    hold starts (the key was down already), so it covers `speed` px every
    second held, then slides `walk_stop_slide`. From rest, it first
    accelerates at `acceleration`, which costs `speed² ÷ 2 acceleration` px
    against a walk at full speed; a hold too short to reach full speed slides
    from the speed it reached.

    Never negative: a character already moving that would slide past
    `distance` is released at once, the least it can travel.

    With an infinite acceleration and deceleration, this is `distance ÷ speed`,
    a walk timed by its length alone.
    """
    if distance <= 0:
        return 0.0
    slide = walk_stop_slide(speed, deceleration)
    if moving:
        return max(0.0, (distance - slide) / speed)
    ramp = speed**2 / (2 * acceleration)
    if distance >= ramp + slide:
        return (distance + ramp - slide) / speed
    # Released before full speed: ½aT² while held, then (aT)² ÷ 2d sliding.
    return math.sqrt(2 * distance / (acceleration * (1 + acceleration / deceleration)))
