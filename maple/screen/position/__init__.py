"""
Where things are on the map, in virtual px (#302, Part 2).

- `CameraReader`: the camera, the virtual coordinate of the play area's
  top-left, matched against the map's static render (`camera`).
"""

from .camera import Camera, CameraReader

__all__ = ["Camera", "CameraReader"]
