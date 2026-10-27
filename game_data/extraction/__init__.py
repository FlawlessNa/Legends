"""
The raw layer: the installed client's Build extracted into a store, losslessly.

It reads the client only through `archive/`, and knows nothing about maps, mobs
or skills. The public API:

- `extract(client, root)`: the client's `Data` folder into the store at `root`,
  as one Extraction (`extract`). It returns what it did, `Extracted`. Its
  catalogue and report hooks are filled in by the layers above.
- `status(client, root)`: `missing`, `fresh` or `stale`, without hashing an
  unchanged client (`status`).
- `Store`: the store's layout, which extraction is the latest, and retention
  (`store`). `Manifest`: one extraction's `manifest.json` (`manifest`).
- `encode_tree`: an image's tree as the raw layer's JSON (`raw`).
- `ImageStore`: the PNG of every canvas, by name (`images`).
- `build_id` and `archive_files`: what identifies a Build (`build`).

`docs/agents/game-data.md` describes the store for anyone reading it directly.
"""

from .build import ArchiveFile, HashedArchive, archive_files, build_id
from .extract import (
    EXTRACTOR_VERSION,
    CatalogueHook,
    Extracted,
    ReportHook,
    extract,
    no_catalogue,
    no_report,
)
from .images import ImageStore, pixel_hash, png
from .manifest import ExtractionError, Failure, Manifest
from .raw import CanvasImage, Json, UnstorableNode, encode_tree
from .status import Freshness, Status, status
from .store import KEEP, Store

__all__ = [
    "EXTRACTOR_VERSION",
    "KEEP",
    "ArchiveFile",
    "CanvasImage",
    "CatalogueHook",
    "Extracted",
    "ExtractionError",
    "Failure",
    "Freshness",
    "HashedArchive",
    "ImageStore",
    "Json",
    "Manifest",
    "ReportHook",
    "Status",
    "Store",
    "UnstorableNode",
    "archive_files",
    "build_id",
    "encode_tree",
    "extract",
    "no_catalogue",
    "no_report",
    "pixel_hash",
    "png",
    "status",
]
