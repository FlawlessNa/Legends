"""
Sprites by path: any canvas's pixels and origin, any vector, a node's
children, and the client font's bytes, from the local store.

- `Sprites`: one extraction's `raw.sqlite` and image store, opened with
  `Sprites.latest(root)` or `Sprites.open(build, root)`. `canvas`, `vector`,
  `children` and `raw_data` look a node up by its path (`sprites`).
- `Sprite`: a canvas's `path`, `rgba` and `origin`.
- `SpriteNotFound`: the path names no such thing. It names the path.

It reads only the raw layer and the stores, never the client, so it works
wherever the store is.
"""

from .sprites import Sprite, SpriteNotFound, Sprites

__all__ = ["Sprite", "SpriteNotFound", "Sprites"]
