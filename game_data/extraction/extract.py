"""
`extract`: the installed client into the store, as one Extraction.

1. **Identify the Build.** Hash every archive and pack (`build`). If the store
   already has this Build, refresh its `extracted_at`, so it becomes the
   latest, and stop: nothing new is created. This is also a rollback.
2. **Write the raw layer** into a hidden folder in `extractions/`: every
   image's tree in `raw.sqlite` (`raw`), and every canvas's image in the shared
   image store (`images`). Each canvas is decoded once: a canvas whose pixels
   another canvas already led to reuses that image, and one named by a
   `_hash` the store has isn't decoded at all.
3. **Build the catalogue**, through the catalogue hook.
4. **Write the manifest, then rename** the folder to `extractions/<build-id>`.
   Until the rename, the store's existing extractions are untouched. If
   anything fails, the folder is deleted and the error raised. Images the
   failed run wrote stay, named by nobody, until the next retention.
5. **Retention** (`store`), then the **report** hook, when an older
   extraction exists.

`raw.sqlite` has two tables:

- `images(path PRIMARY KEY, sha256, tree)`: every image, by its path such as
  `Map/Map/Map0/000001000.img`. `tree` is its JSON (`raw`), and `sha256` is the
  SHA-256 of that text, so it changes exactly when the stored tree does.
- `canvas_images(name PRIMARY KEY)`: every image in the image store that a
  canvas names, which is what retention keeps.

**Failures.** A canvas whose `_outlink` or `_inlink` names nothing
(`BrokenLink`) is recorded in the manifest and the result, with `image: null`
in its tree, and extraction carries on. Any other error stops it.
"""

import hashlib
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from game_data.archive import (
    BrokenLink,
    CanvasNode,
    ClientData,
    CorruptArchive,
    Image,
    ImageEntry,
    Pixels,
    PropertyNode,
    StringNode,
)
from game_data.config import STORE

from .build import archive_files, build_id, hash_archives
from .images import ImageStore, is_name, pixel_hash
from .manifest import MANIFEST, ExtractionError, Failure, Manifest
from .raw import CanvasImage, Json, UnstorableNode, dumps, encode_tree
from .store import RAW, TEMPORARY, Store

EXTRACTOR_VERSION = 1
HASH = "_hash"

type CatalogueHook = Callable[[Path, ImageStore], int | None]
"""Builds the catalogue in an extraction's folder; returns its schema version."""

type ReportHook = Callable[[Store, str, str], Path | None]
"""Writes the report from one build to another; returns the report's path."""

type Progress = Callable[[int, int], None]
"""Told how many images are done, of how many."""


def no_catalogue(extraction: Path, images: ImageStore) -> int | None:
    """The catalogue hook until there is a catalogue: builds nothing."""
    del extraction, images
    return None


def no_report(store: Store, old: str, new: str) -> Path | None:
    """The report hook until there is a report: writes nothing."""
    del store, old, new
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Extracted:
    """
    What `extract` did.

    :ivar manifest: The extraction's manifest, now the latest.
    :ivar created: Whether the extraction is new, rather than a Build the
        store already had.
    :ivar written: How many images were added to the image store.
    :ivar report: The report's path, when one was written.
    :ivar seconds: How long it took.
    """

    manifest: Manifest
    created: bool
    written: int
    report: Path | None
    seconds: float


def extract(
    client: Path,
    root: Path = STORE,
    *,
    catalogue: CatalogueHook = no_catalogue,
    report: ReportHook = no_report,
    progress: Progress | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> Extracted:
    """
    Extracts the client's `Data` folder into the store at `root`.

    :param catalogue: Called with the new extraction's folder before it is
        renamed into place.
    :param report: Called after retention, with the previous latest build and
        the new one, when the store had an extraction of another Build.
    :param progress: Called after each image.
    :param now: The clock `extracted_at` is read from.
    :raises ArchiveError: The client's files don't read; nothing is kept.
    :raises ExtractionError: The client has no archives, or a tree can't be
        stored; nothing is kept.
    """
    started = time.perf_counter()
    store = Store(root)
    store.clear_temporary()
    archives = hash_archives(client, archive_files(client))
    if not archives:
        raise ExtractionError(f"{client} has no .wz archives or .ms packs")
    build = build_id(archives)
    previous = store.latest()

    if (store.extraction(build) / MANIFEST).is_file():
        manifest = replace(Manifest.read(store.extraction(build)), extracted_at=now())
        manifest.write(store.extraction(build))
        store.retain()
        return Extracted(manifest, False, 0, None, time.perf_counter() - started)

    folder = store.extractions / f"{TEMPORARY}{build}-{os.getpid()}"
    try:
        folder.mkdir(parents=True)
        raw = _RawWriter(ClientData(client), store.images)
        raw.write(folder / RAW, progress)
        manifest = Manifest(
            build=build,
            extractor_version=EXTRACTOR_VERSION,
            catalogue_schema_version=catalogue(folder, store.images),
            extracted_at=now(),
            archives=tuple(archives),
            images=raw.images,
            canvases=raw.canvases,
            failures=tuple(raw.failures),
        )
        manifest.write(folder)
        folder.rename(store.extraction(build))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    store.retain()
    report_path = report(store, previous.build, build) if previous else None
    return Extracted(
        manifest, True, raw.written, report_path, time.perf_counter() - started
    )


class _RawWriter:
    """Writes one `raw.sqlite`, and the images its canvases name."""

    def __init__(self, client: ClientData, images: ImageStore) -> None:
        self._client = client
        self._images = images
        # The image each pixel source's canvas became, by the source's path.
        self._by_source: dict[str, str] = {}
        self.referenced: set[str] = set()
        self.failures: list[Failure] = []
        self.images = 0
        self.canvases = 0
        self.written = 0

    def write(self, database: Path, progress: Progress | None) -> None:
        images = list(self._client.root.walk())
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA journal_mode = OFF")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute(
                "CREATE TABLE images ("
                "path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, tree TEXT NOT NULL)"
            )
            connection.execute("CREATE TABLE canvas_images (name TEXT PRIMARY KEY)")
            for done, image in enumerate(images, start=1):
                tree = dumps(self._tree(image))
                sha256 = hashlib.sha256(tree.encode()).hexdigest()
                connection.execute(
                    "INSERT INTO images VALUES (?, ?, ?)", (image.path, sha256, tree)
                )
                self.images += 1
                if progress is not None:
                    progress(done, len(images))
            connection.executemany(
                "INSERT INTO canvas_images VALUES (?)",
                ((name,) for name in sorted(self.referenced)),
            )
            connection.commit()

    def _tree(self, image: Image) -> dict[str, Json]:
        root = self._client.node(image.path)
        if not isinstance(root, PropertyNode):
            raise CorruptArchive(
                image.archive, image.name, "", f"its root is a {root.type}"
            )
        payloads = _Payloads(image)
        try:
            return encode_tree(
                root,
                canvas=lambda path, node: self._canvas(image, path, node),
                payload_sha256=payloads.sha256,
            )
        except UnstorableNode as error:
            raise ExtractionError(
                f"archive {image.archive}, image {image.path}: {error}"
            ) from error

    def _canvas(self, image: Image, path: str, node: CanvasNode) -> CanvasImage:
        self.canvases += 1
        try:
            found = self._client.canvas_source(f"{image.path}/{path}")
        except BrokenLink as error:
            self.failures.append(Failure(image.path, path, str(error)))
            return CanvasImage(None, node.canvas.width, node.canvas.height)
        given = node.children.get(HASH)
        if given is not None:
            if not isinstance(given, StringNode) or not is_name(given.value):
                raise ExtractionError(
                    f"archive {image.archive}, image {image.path}, node "
                    f"{path}/{HASH}: it isn't 64 lowercase hex digits"
                )
            name = given.value
            if not self._images.has(name):
                self._write(name, found.pixels())
        else:
            known = self._by_source.get(found.source)
            if known is None:
                pixels = found.pixels()
                known = pixel_hash(pixels)
                self._by_source[found.source] = known
                self._write(known, pixels)
            name = known
        self.referenced.add(name)
        return CanvasImage(name, found.ref.width, found.ref.height)

    def _write(self, name: str, pixels: Pixels) -> None:
        if self._images.write(name, pixels):
            self.written += 1


class _Payloads:
    """The SHA-256 of a sound's or raw data's bytes, read with the image's."""

    def __init__(self, image: Image) -> None:
        self._image = image
        self._data: bytes | None = None
        # A `.wz` image's references count from the start of the file, a
        # pack's from the image's first byte (`MsPack.parse`).
        entry = image.entry
        self._base = entry.offset if isinstance(entry, ImageEntry) else 0

    def sha256(self, offset: int, length: int) -> str:
        if self._data is None:
            self._data = self._image.read()
        start = offset - self._base
        chunk = self._data[start : start + length]
        if start < 0 or len(chunk) != length:
            raise CorruptArchive(
                self._image.archive,
                self._image.name,
                None,
                f"{length} bytes at offset {offset} are outside the image",
            )
        return hashlib.sha256(chunk).hexdigest()
