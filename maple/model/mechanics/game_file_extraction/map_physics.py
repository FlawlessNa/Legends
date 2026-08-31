import numpy as np
from enum import Enum

# Physics constants sourced from Physics.img.xml (GMS v83).
# These are game-engine constants; they do not vary per map or per character.
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
    FLY_FORCE = 120000.0
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


class VRPhysics:
    """
    Implements traditional kinetic physics.
    """
    JUMP_HEIGHT = _CONSTANTS.JUMP_SPEED.value ** 2 / (2 * _CONSTANTS.GRAVITY_ACC.value)
    JUMP_DURATION = 2 * _CONSTANTS.JUMP_SPEED.value / _CONSTANTS.GRAVITY_ACC.value
    JUMP_WIDTH = JUMP_DURATION * _CONSTANTS.WALK_SPEED.value


class MinimapPhysics:
    """
    Implements physics for the minimap.
    """
    def __init__(self, scale_x: float, scale_y: float):
        self.minimap_speed = _CONSTANTS.WALK_SPEED.value * scale_x
        self.jump_height = VRPhysics.JUMP_HEIGHT * scale_y
        self.jump_distance = VRPhysics.JUMP_WIDTH * scale_x
        self.teleport_h_dist = _CONSTANTS.TELEPORT_DISTANCE.value * scale_x
        self.teleport_v_up_dist = self.teleport_h_dist - 1  # TODO FIGURE THIS OUT
        self.teleport_v_down_dist = self.teleport_h_dist + 2  # TODO FIGURE THIS OUT

    def get_jump_height(self, multiplier: float = 1.00) -> float:
        return self.jump_height * (multiplier ** 2)

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
        fall: bool = False
    ) -> list[tuple[int, int]]:
        assert direction in ["left", "right"], "Invalid direction for trajectory."
        x_values = np.arange(x_start, map_width, 0.01)
        if fall:
            y_values = y_start - self._jump_parabola_y(
                x_values - x_start + jump_dist / 2,
                jump_dist,
                jump_height,
            ) + jump_height
        else:
            y_values = y_start - self._jump_parabola_y(
                x_values - x_start,
                jump_dist,
                jump_height
            )
        if direction == 'left':
            x_values = np.linspace(
                x_start,
                x_start - (x_values[-1] - x_start),
                len(y_values)
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
    def _jump_parabola_y(x, jump_distance: float, jump_height: float):
        h, k = jump_distance / 2, jump_height
        a = k / h ** 2
        return -a * (x - h) ** 2 + k