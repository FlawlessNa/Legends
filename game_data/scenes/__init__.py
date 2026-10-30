"""
Scenes: synthetic client screens of a map, with its mobs drawn on their
spawns, and a label per mob, for training a detection model. They're drawn
from the catalogue and the image store, never the client, and know nothing of
any model or its training.

The public API (`compose`):

- `compose_scene(cat, map, rng, ...)`: one `Scene`, an RGB image of the
  client's size and a `Label(cls, box, visible)` per mob drawn above the
  visibility floor.
- `draw_mobs(view, placements, images, overlays)`: draws `Placement`s over a
  view, then `Overlay`s over them, and labels each mob, the step
  `compose_scene` draws its mobs through.
- `occluders`: the drops and damage numbers `compose_scene` draws over mobs
  when its `occluders` asks for them, laid out as `Overlay`s. `OCCLUDERS`
  names their kinds.
- `draw_camera`: a scene's camera, drawn inside the map's VR bounds.
- `class_name`: a mob's class, its name with spaces and dots removed, the form
  the bot compares a model's classes with.
- `map_classes`: the classes a map's scenes can label, sorted by name.
- `SCENES_VERSION`: bumped whenever the same arguments and seed would give
  another scene.
- `SceneError`: two species of a map share a class name.

Players (`players`), a feasibility composer not yet drawn in scenes:

- `Wardrobe(cat).compose(outfit, action, frame, name=..., tag=...)`: one
  character from `Character.wz`, its parts anchored by their `map` points,
  with a name tag under it, as a `Player`.
- `Outfit`: what it wears, `Outfit.drawn(rng)` drawing it from `PIECES`.

Players and the UI aren't drawn in scenes.
"""

from . import occluders
from .compose import (
    ACTIONS,
    FLY_LIFT,
    MOBS,
    SCENES_VERSION,
    VISIBILITY_FLOOR,
    Label,
    Placement,
    Scene,
    SceneError,
    class_name,
    compose_scene,
    draw_camera,
    draw_mobs,
    map_classes,
)
from .occluders import KINDS as OCCLUDERS
from .occluders import Overlay
from .players import (
    PIECES,
    PLAYER_ACTIONS,
    SKINS,
    SLOTS,
    Outfit,
    Player,
    Wardrobe,
)

__all__ = [
    "ACTIONS",
    "FLY_LIFT",
    "MOBS",
    "OCCLUDERS",
    "PIECES",
    "PLAYER_ACTIONS",
    "SCENES_VERSION",
    "SKINS",
    "SLOTS",
    "VISIBILITY_FLOOR",
    "Label",
    "Outfit",
    "Overlay",
    "Placement",
    "Player",
    "Scene",
    "SceneError",
    "Wardrobe",
    "class_name",
    "compose_scene",
    "draw_camera",
    "draw_mobs",
    "map_classes",
    "occluders",
]
