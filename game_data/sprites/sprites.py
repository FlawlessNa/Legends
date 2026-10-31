"""
`Sprites`: the nodes of one extraction's images, by path.

A path is an image's path, then the node's path inside it, with the client's
real node names, type prefixes included:

    UI/StatusBar.img/canvas:gaugeLabel
    UI/StatusBar.img/gauge/vector:posNumberHp
    Map/MapHelper.img/minimap/user
    Map/Map/Map1/100000000.img/miniMap/canvas

The image's path is everything up to the first step that ends in `.img`. Links
are followed on the way and at the end (`Tree.resolved`), so a canvas reached
through a UOL is the canvas it leads to.

Each image's tree is parsed once per instance. A path that names no image, no
node, a node of the wrong type, or a canvas whose pixels the client's files
didn't lead to (`image: null`) raises `SpriteNotFound`, naming the path.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

import numpy as np

from game_data.catalogue.trees import CatalogueError, Tree
from game_data.config import STORE
from game_data.extraction import RAW, ExtractionError, Manifest, Store

IMAGE = ".img"


class SpriteNotFound(LookupError):
    """A path names no such image, node, canvas, vector or raw data."""


@dataclass(frozen=True, slots=True, eq=False)
class Sprite:
    """
    A canvas.

    :ivar path: The path it was asked for by.
    :ivar rgba: Its pixels, `H×W×4` `uint8` in RGBA order. Read-only.
    :ivar origin: Its `(x, y)` origin, `(0, 0)` when it has none.
    """

    path: str
    rgba: np.ndarray
    origin: tuple[int, int]


class Sprites:
    """
    One extraction's sprites. Open one with `latest` or `open`.

    :ivar build: The extraction's build id.
    :ivar store: The store it's in, whose image and blob stores hold the
        pixels and the font.
    """

    def __init__(self, build: str, database: sqlite3.Connection, store: Store) -> None:
        self.build = build
        self.store = store
        self._db = database
        self._trees: dict[str, Tree | None] = {}

    @classmethod
    def latest(cls, root: Path = STORE) -> Self:
        """
        The latest extraction's sprites.

        :raises CatalogueError: The store has no extraction.
        """
        manifest = Store(root).latest()
        if manifest is None:
            raise CatalogueError(
                f"{root} has no extraction; run `python -m game_data extract`"
            )
        return cls.open(manifest.build, root)

    @classmethod
    def open(cls, build: str, root: Path = STORE) -> Self:
        """
        The sprites of the extraction of `build`.

        :raises CatalogueError: The store has no such extraction.
        """
        store = Store(root)
        folder = store.extraction(build)
        try:
            Manifest.read(folder)
        except ExtractionError as error:
            raise CatalogueError(f"{root} has no extraction {build}") from error
        raw = (folder / RAW).resolve()
        database = sqlite3.connect(f"{raw.as_uri()}?mode=ro", uri=True)
        return cls(build, database, store)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()

    def canvas(self, path: str) -> Sprite:
        """
        The canvas at `path`: its pixels and origin.

        :raises SpriteNotFound: The path names no canvas, or its pixels.
        """
        node = self._node(path)
        try:
            node.expect("canvas")
            name = node.canvas_image()
            origin = node.origin()
        except CatalogueError as error:
            raise SpriteNotFound(f"{path}: {error}") from error
        if name is None:
            raise SpriteNotFound(f"{path}: its pixels weren't found (image is null)")
        try:
            rgba = self.store.images.read(name)
        except (OSError, ValueError) as error:
            raise SpriteNotFound(
                f"{path}: its image {name} can't be read: {error}"
            ) from error
        rgba.flags.writeable = False
        return Sprite(path, rgba, origin)

    def vector(self, path: str) -> tuple[int, int]:
        """
        The `(x, y)` of the vector at `path`.

        :raises SpriteNotFound: The path names no vector.
        """
        node = self._node(path)
        try:
            return node.vector()
        except CatalogueError as error:
            raise SpriteNotFound(f"{path}: {error}") from error

    def children(self, path: str) -> list[str]:
        """
        The names of the node's children, in the client's order. A canvas's
        properties, such as `origin`, are among them. An image's path gives
        the names at its top.

        :raises SpriteNotFound: The path names nothing, or a node that has no
            children, such as a number.
        """
        node = self._node(path)
        if not isinstance(node.value, dict):
            raise SpriteNotFound(f"{path}: it is a {node.type}, which has no children")
        return [name for name, _ in node.children()]

    def raw_data(self, path: str) -> bytes:
        """
        The bytes of the raw-data node at `path`. `extract` writes them only
        for the nodes under `UI/Font/`.

        :raises SpriteNotFound: The path names no raw data.
        :raises CatalogueError: The store lacks the blob, or it doesn't match
            its SHA-256.
        """
        node = self._node(path)
        try:
            node.expect("raw_data")
            sha256 = node.at_text("sha256")
        except CatalogueError as error:
            raise SpriteNotFound(f"{path}: {error}") from error
        file = self.store.blobs.path(sha256)
        try:
            data = file.read_bytes()
        except OSError as error:
            raise CatalogueError(
                f"{path}: the store has no blob {sha256}; run "
                "`python -m game_data extract`"
            ) from error
        if hashlib.sha256(data).hexdigest() != sha256:
            raise CatalogueError(f"{path}: the blob {file} doesn't match its SHA-256")
        return data

    def _node(self, path: str) -> Tree:
        steps = path.split("/")
        end = next((i for i, step in enumerate(steps) if step.endswith(IMAGE)), None)
        if end is None:
            raise SpriteNotFound(f"{path}: it names no image (a step ending in .img)")
        image = "/".join(steps[: end + 1])
        node = self._tree(image)
        if node is None:
            raise SpriteNotFound(f"{path}: the store has no image {image}")
        for step in steps[end + 1 :]:
            found = node.get(step)
            if found is None:
                raise SpriteNotFound(f"{path}: {image} has no node at {step!r}")
            try:
                node = found.resolved()
            except CatalogueError as error:
                raise SpriteNotFound(f"{path}: {error}") from error
        return node

    def _tree(self, image: str) -> Tree | None:
        if image not in self._trees:
            row = self._db.execute(
                "SELECT tree FROM images WHERE path = ?", (image,)
            ).fetchone()
            self._trees[image] = (
                None if row is None else Tree.of(image, json.loads(row[0]))
            )
        return self._trees[image]
