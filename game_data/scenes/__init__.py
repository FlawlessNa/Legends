"""
Scenes: synthetic client screens of a map, with its mobs drawn on their
spawns, and a label per mob, for training a detection model. They're drawn
from the catalogue and the image store, never the client, and know nothing of
any model or its training.

The public API (`compose`):

- `compose_scene(cat, map, rng, ...)`: one `Scene`, an RGB image of the
  client's size and a `Label(cls, box, visible)` per mob drawn above the
  visibility floor.
- `draw_mobs(view, placements, images)`: draws `Placement`s over a view and
  labels each, the step `compose_scene` draws its mobs through.
- `draw_camera`: a scene's camera, drawn inside the map's VR bounds.
- `class_name`: a mob's class, its name with spaces and dots removed, the form
  the bot compares a model's classes with.
- `SCENES_VERSION`: bumped whenever the same arguments and seed would give
  another scene.
- `SceneError`: two species of a map share a class name.

No occluders are drawn yet.
"""

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
)

__all__ = [
    "ACTIONS",
    "FLY_LIFT",
    "MOBS",
    "SCENES_VERSION",
    "VISIBILITY_FLOOR",
    "Label",
    "Placement",
    "Scene",
    "SceneError",
    "class_name",
    "compose_scene",
    "draw_camera",
    "draw_mobs",
]
