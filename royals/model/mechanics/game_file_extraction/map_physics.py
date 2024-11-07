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


class VRPhysics:
    """
    Implements traditional kinetic physics.
    """
    pass


class MinimapPhysics:
    """
    Implements physics for the minimap.
    """
    def __init__(self, minimap: ...):
        self.minimap_speed = ...
        self.jump_height = ...
        self.jump_distance = ...
        self.teleport_h_dist = ...
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
