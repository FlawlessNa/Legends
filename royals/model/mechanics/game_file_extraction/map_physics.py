import numpy as np
import os
import xml.etree.ElementTree as ET
from enum import Enum
from paths import ROOT

PHYS_XML_PATH = os.path.join(ROOT, "royals/assets/game_files/Physics.img.xml")
PHYS_XML = ET.parse(PHYS_XML_PATH).getroot()
PHYS = {child.attrib['name']: float(child.attrib['value']) for child in PHYS_XML}


class _PhysicsValues(Enum):
    WALK_FORCE = PHYS["walkForce"]
    WALK_SPEED = PHYS["walkSpeed"]
    WALK_DRAG = PHYS["walkDrag"]
    SLIP_FORCE = PHYS["slipForce"]
    SLIP_SPEED = PHYS["slipSpeed"]
    FLOAT_DRAG_1 = PHYS["floatDrag1"]
    FLOAT_DRAG_2 = PHYS["floatDrag2"]
    FLOAT_COEFFICIENT = PHYS["floatCoefficient"]
    SWIM_FORCE = PHYS["swimForce"]
    SWIM_SPEED = PHYS["swimSpeed"]
    FLY_FORCE = PHYS["flyForce"]
    FLY_SPEED = PHYS["flySpeed"]
    GRAVITY_ACC = PHYS["gravityAcc"]
    FALL_SPEED = PHYS["fallSpeed"]
    JUMP_SPEED = PHYS["jumpSpeed"]
    MAX_FRICTION = PHYS["maxFriction"]
    MIN_FRICTION = PHYS["minFriction"]
    SWIM_SPEED_DEC = PHYS["swimSpeedDec"]
    FLY_JUMP_DEC = PHYS["flyJumpDec"]
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
        self.teleport_v_up_dist = ...
        self.teleport_v_down_dist = ...

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
        map_height: int
    ) -> list[tuple[int, int]]:
        assert direction in ["left", "right"], "Invalid direction for trajectory."
        x_values = np.arange(x_start, map_width, 0.01)
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