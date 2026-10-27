"""
An extraction's `manifest.json`: which Build it is, and how it was made.

    {
      "build": "0123456789abcdef",
      "extractor_version": 1,
      "catalogue_schema_version": null,
      "extracted_at": "2026-10-26T12:00:00.000000+00:00",
      "archives": {"Map/Map.wz": {"size": 1, "mtime_ns": 2, "sha256": "..."}},
      "images": 14623,
      "canvases": 689343,
      "failures": [{"image": "...", "node": "...", "reason": "..."}]
    }

`catalogue_schema_version` is `null` until a catalogue is built. `failures`
are the canvases whose link to their pixels names nothing: the one kind of
failure an extraction records and carries on past (`BrokenLink`).
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .build import HashedArchive

MANIFEST = "manifest.json"


class ExtractionError(Exception):
    """The store, or something in it, isn't as an extraction expects."""


@dataclass(frozen=True, slots=True)
class Failure:
    """
    A canvas whose pixels couldn't be found, recorded and carried past.

    :ivar image: The image's path, such as `Character/Weapon/01302000.img`.
    :ivar node: The canvas's path inside the image.
    :ivar reason: Why, naming the archive and the link.
    """

    image: str
    node: str
    reason: str


@dataclass(frozen=True, slots=True)
class Manifest:
    """
    :ivar build: The build id.
    :ivar extractor_version: The version of the code that wrote the raw layer.
    :ivar catalogue_schema_version: `None` until a catalogue is built.
    :ivar extracted_at: When it was last extracted, in UTC. Re-extracting the
        same Build refreshes it.
    :ivar archives: Every archive and pack, by path.
    :ivar images: How many images the raw layer holds.
    :ivar canvases: How many canvases they hold.
    :ivar failures: The canvases whose pixels couldn't be found.
    """

    build: str
    extractor_version: int
    catalogue_schema_version: int | None
    extracted_at: datetime
    archives: tuple[HashedArchive, ...]
    images: int
    canvases: int
    failures: tuple[Failure, ...]

    def write(self, folder: Path) -> None:
        """Writes `manifest.json` into `folder`, replacing it in one step."""
        target = folder / MANIFEST
        temporary = folder / f"{MANIFEST}.{os.getpid()}.tmp"
        temporary.write_text(
            json.dumps(self._json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)

    def _json(self) -> dict[str, object]:
        return {
            "build": self.build,
            "extractor_version": self.extractor_version,
            "catalogue_schema_version": self.catalogue_schema_version,
            "extracted_at": self.extracted_at.isoformat(timespec="microseconds"),
            "archives": {
                archive.path: {
                    "size": archive.size,
                    "mtime_ns": archive.mtime_ns,
                    "sha256": archive.sha256,
                }
                for archive in self.archives
            },
            "images": self.images,
            "canvases": self.canvases,
            "failures": [
                {"image": f.image, "node": f.node, "reason": f.reason}
                for f in self.failures
            ],
        }

    @classmethod
    def read(cls, folder: Path) -> Manifest:
        """
        The manifest in `folder`.

        :raises ExtractionError: It's missing or malformed.
        """
        file = folder / MANIFEST
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            return cls(
                build=raw["build"],
                extractor_version=raw["extractor_version"],
                catalogue_schema_version=raw["catalogue_schema_version"],
                extracted_at=datetime.fromisoformat(raw["extracted_at"]),
                archives=tuple(
                    HashedArchive(
                        path=path,
                        size=entry["size"],
                        mtime_ns=entry["mtime_ns"],
                        sha256=entry["sha256"],
                    )
                    for path, entry in raw["archives"].items()
                ),
                images=raw["images"],
                canvases=raw["canvases"],
                failures=tuple(
                    Failure(image=f["image"], node=f["node"], reason=f["reason"])
                    for f in raw["failures"]
                ),
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ExtractionError(f"{file} can't be read: {error!r}") from error
