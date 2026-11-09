"""
Where the character is (epic #302 Part 2, item 4): the readers that place it
on screen and on the map.

`camera` places the play area on the map: the camera, the virtual coordinate
of its top-left, matched against the map's static render (`CameraReader`).
`characters` finds the characters' feet on screen, in client px
(`CharacterFinder`). Turning those into virtual px, with the camera and the
play area's render size, is `PositionFusion`'s job (#392).
"""

from .camera import Camera, CameraReader
from .characters import (
    CharacterFinder,
    CharacterSighting,
    NameTagFinder,
    YoloCharacterFinder,
    tag_upscale,
)

__all__ = [
    "Camera",
    "CameraReader",
    "CharacterFinder",
    "CharacterSighting",
    "NameTagFinder",
    "YoloCharacterFinder",
    "tag_upscale",
]
