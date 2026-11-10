"""
Where the character is (epic #302 Part 2, item 4): the readers that place it
on screen and on the map.

`camera` places the play area on the map: the camera, the virtual coordinate
of its top-left, matched against the map's static render (`CameraReader`).
`characters` finds the characters' feet on screen, in client px
(`CharacterFinder`). `fusion` turns them into virtual px, with the camera and
the play area's render size, and checks them against the minimap's position
(`PositionFusion`, `Reading[VirtualPosition]`).
"""

from .camera import PLAY_AREAS, Camera, CameraReader, play_area_size
from .characters import (
    CharacterFinder,
    CharacterSighting,
    NameTagFinder,
    YoloCharacterFinder,
    tag_upscale,
)
from .fusion import (
    WINDOW,
    Fusion,
    PositionFusion,
    PositionSource,
    VirtualPosition,
)

__all__ = [
    "PLAY_AREAS",
    "WINDOW",
    "Camera",
    "CameraReader",
    "CharacterFinder",
    "CharacterSighting",
    "Fusion",
    "NameTagFinder",
    "PositionFusion",
    "PositionSource",
    "VirtualPosition",
    "YoloCharacterFinder",
    "play_area_size",
    "tag_upscale",
]
