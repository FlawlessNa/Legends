"""
Movement physics.

`VRPhysics` is the character's movement in virtual px (`CONTEXT.md` ->
Virtual coordinates): walk speed, climb speed, jump arc and teleport reach.
Walk and jump come from the game files (`Map/Physics.img`, through
`Catalogue.physics()`), times the character's speed and jump multipliers.
Climb and teleport are not in the game files, so they start from named
constants until Trials measure them (#397). Each value is then multiplied by
its Calibration constant (`Calibration`).

Movement Plans are planned and compiled on it (#396), with the character's
current speed and jump multipliers: a bot reads `Physics.img` once
(`game_physics`) and builds a `VRPhysics` from it whenever it plans, so a
change of stat reaches the next Path.

`MinimapPhysics` is the minimap-pixel model the grid still runs on, until #399
removes it with the hard-coded table it reads.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from game_data.catalogue import Catalogue
from game_data.config import STORE

#: Virtual px one teleport moves the character. Not in `Physics.img`: it
#: starts from today's `TELEPORT_DISTANCE` (below), until measured by #397.
TELEPORT_REACH = 150.0

#: Virtual px/s the character climbs a rope or ladder at. Not in
#: `Physics.img`: `compile_movements` times climbs at the walk speed today
#: (`walkSpeed`, 125), so it starts there, until measured by #397.
CLIMB_SPEED = 125.0

#: The `Physics.img` keys `VRPhysics` reads.
PHYSICS_KEYS = ("walkSpeed", "jumpSpeed", "gravityAcc", "fallSpeed")

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
    """

    walk_speed: float
    jump_speed: float
    gravity: float
    fall_speed: float
    climb_speed: float
    teleport_reach: float

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
        today. Gravity and the fall speed are the game's own.

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


# The hard-coded table `MinimapPhysics` still reads, from Physics.img.xml
# (GMS v83), until #399 removes both. `VRPhysics` reads the game files instead.
class _PhysicsValues(Enum):
    WALK_FORCE = 140000.0
    WALK_SPEED = 125.0
    WALK_DRAG = 80000.0
    SLIP_FORCE = 60000.0
    SLIP_SPEED = 120.0
    FLOAT_DRAG_1 = 100000.0
    FLOAT_DRAG_2 = 10000.0
    FLOAT_COEFFICIENT = 0.01
    SWIM_FORCE = 120000.0
    SWIM_SPEED = 140.0
    FLY_FORCE = 120000.0  # noqa: PIE796 - same value as SWIM_FORCE in the client
    FLY_SPEED = 200.0
    GRAVITY_ACC = 2000.0
    FALL_SPEED = 670.0
    JUMP_SPEED = 555.0
    MAX_FRICTION = 2.0
    MIN_FRICTION = 0.05
    SWIM_SPEED_DEC = 0.9
    FLY_JUMP_DEC = 0.35
    TELEPORT_DISTANCE = 150


_CONSTANTS = _PhysicsValues


# What `VRPhysics.JUMP_HEIGHT` and `JUMP_WIDTH` were, from the table above.
_JUMP_HEIGHT = _CONSTANTS.JUMP_SPEED.value**2 / (2 * _CONSTANTS.GRAVITY_ACC.value)
_JUMP_DURATION = 2 * _CONSTANTS.JUMP_SPEED.value / _CONSTANTS.GRAVITY_ACC.value
_JUMP_WIDTH = _JUMP_DURATION * _CONSTANTS.WALK_SPEED.value


class MinimapPhysics:
    """
    Implements physics for the minimap.
    """

    def __init__(self, scale_x: float, scale_y: float) -> None:
        self.minimap_speed = _CONSTANTS.WALK_SPEED.value * scale_x
        self.jump_height = _JUMP_HEIGHT * scale_y
        self.jump_distance = _JUMP_WIDTH * scale_x
        self.teleport_h_dist = _CONSTANTS.TELEPORT_DISTANCE.value * scale_x
        self.teleport_v_up_dist = self.teleport_h_dist - 1  # TODO FIGURE THIS OUT
        self.teleport_v_down_dist = self.teleport_h_dist + 2  # TODO FIGURE THIS OUT

    def get_jump_height(self, multiplier: float = 1.00) -> float:
        return self.jump_height * (multiplier**2)

    def get_jump_distance(
        self, speed_multiplier: float = 1.00, jump_multiplier: float = 1.00
    ) -> float:
        return self.jump_distance * speed_multiplier * jump_multiplier

    def get_minimap_speed(self, speed_multiplier: float = 1.00) -> float:
        return self.minimap_speed * speed_multiplier

    def get_jump_trajectory(
        self,
        x_start: int,
        y_start: int,
        direction: str,
        jump_dist: float,
        jump_height: float,
        map_width: int,
        map_height: int,
        fall: bool = False,
    ) -> list[tuple[int, int]]:
        assert direction in ["left", "right"], "Invalid direction for trajectory."
        x_values = np.arange(x_start, map_width, 0.01)
        if fall:
            y_values = (
                y_start
                - self._jump_parabola_y(
                    x_values - x_start + jump_dist / 2,
                    jump_dist,
                    jump_height,
                )
                + jump_height
            )
        else:
            y_values = y_start - self._jump_parabola_y(
                x_values - x_start, jump_dist, jump_height
            )
        if direction == "left":
            x_values = np.linspace(
                x_start, x_start - (x_values[-1] - x_start), len(y_values)
            )
        # Now truncate the arrays such that they only contain points within the map area
        mask = (
            (x_values >= 0)
            & (x_values <= map_width)
            & (y_values >= 0)
            & (y_values <= map_height)
        )
        x_values = x_values[mask].astype(int)
        y_values = y_values[mask].astype(int)

        # The rounding may cause adjacent cells to be only connected diagonally.
        # Add buffer in such cases.
        buffered_x_values = []
        buffered_y_values = []
        for i in range(len(x_values) - 1):
            buffered_x_values.append(x_values[i])
            buffered_y_values.append(y_values[i])
            dx = x_values[i + 1] - x_values[i]
            dy = y_values[i + 1] - y_values[i]
            if abs(dx) == abs(dy) == 1:
                buffered_x_values.append(x_values[i] + np.sign(dx))
                buffered_y_values.append(y_values[i])
                buffered_x_values.append(x_values[i])
                buffered_y_values.append(y_values[i] + np.sign(dy))
        buffered_x_values.append(x_values[-1])
        buffered_y_values.append(y_values[-1])
        x_values = np.array(buffered_x_values)
        y_values = np.array(buffered_y_values)

        trajectory = list(zip(x_values.astype(int), y_values.astype(int)))
        return sorted(set(trajectory), key=trajectory.index)

    @staticmethod
    def _jump_parabola_y(
        x: np.ndarray, jump_distance: float, jump_height: float
    ) -> np.ndarray:
        h, k = jump_distance / 2, jump_height
        a = k / h**2
        return -a * (x - h) ** 2 + k
