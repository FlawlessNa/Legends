"""
Where the character is (epic #302 Part 2, item 4): the readers that place it
on screen and on the map.

`characters` finds the characters' feet on screen, in client px
(`CharacterFinder`). Turning those into virtual px, with the camera and the
play area's render size, is `PositionFusion`'s job (#392).
"""

from .characters import (
    CharacterFinder,
    CharacterSighting,
    NameTagFinder,
    YoloCharacterFinder,
    tag_upscale,
)

__all__ = [
    "CharacterFinder",
    "CharacterSighting",
    "NameTagFinder",
    "YoloCharacterFinder",
    "tag_upscale",
]
