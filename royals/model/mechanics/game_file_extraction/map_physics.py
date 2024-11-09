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
