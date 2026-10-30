"""
The store's layout, which extraction is the latest, and retention.

    <root>/                              data/game_data by default
      extractions/<build-id>/
        manifest.json                    the Build, and how it was extracted
        raw.sqlite                       every image's tree (`extract`)
        catalogue.sqlite                 the typed layer, once it exists
      images/<hh>/<name>.png             every canvas's image, shared (`images`)
      reports/<old>__<new>.html          the patch reports, once they exist

**Latest** is the extraction with the newest `extracted_at`. A folder in
`extractions/` is an extraction only once it has its manifest: one being
written is a hidden folder (`.tmp-...`) until it is complete and renamed.

**Retention** keeps the `KEEP` latest extractions and deletes the rest. Then it
deletes every image no kept extraction names, every file in `images/` that
isn't an image, and every report that names an extraction no longer kept.
Only one extraction may run on a store at a time.
"""

import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .images import ImageStore
from .manifest import MANIFEST, Manifest

KEEP = 2
EXTRACTIONS = "extractions"
IMAGES = "images"
REPORTS = "reports"
RAW = "raw.sqlite"
TEMPORARY = ".tmp-"

_REPORT = re.compile(r"(?P<old>[0-9a-f]+)__(?P<new>[0-9a-f]+)\.html")


class Store:
    """
    A store of extractions, at `root`. Nothing is created until written.

    :param root: Resolved here, once: a relative root is taken from the working
        directory, and every path below it is absolute (`referenced_images`
        opens `raw.sqlite` by its `file:` URI, which needs one).
    """

    def __init__(self, root: Path) -> None:
        root = root.resolve()
        self.root = root
        self.extractions = root / EXTRACTIONS
        self.images = ImageStore(root / IMAGES)
        self.reports = root / REPORTS

    def extraction(self, build: str) -> Path:
        return self.extractions / build

    def manifests(self) -> list[Manifest]:
        """Every extraction's manifest, the latest first."""
        if not self.extractions.is_dir():
            return []
        found = [
            Manifest.read(folder)
            for folder in self.extractions.iterdir()
            if folder.is_dir()
            and not folder.name.startswith(".")
            and (folder / MANIFEST).is_file()
        ]
        return sorted(found, key=lambda m: m.extracted_at, reverse=True)

    def latest(self) -> Manifest | None:
        manifests = self.manifests()
        return manifests[0] if manifests else None

    def clear_temporary(self) -> None:
        """Deletes what a run that died left in `extractions/`."""
        if not self.extractions.is_dir():
            return
        for folder in self.extractions.iterdir():
            if folder.name.startswith(TEMPORARY):
                shutil.rmtree(folder)

    def retain(self) -> None:
        """Keeps the `KEEP` latest extractions, and deletes what nothing needs."""
        manifests = self.manifests()
        for manifest in manifests[KEEP:]:
            shutil.rmtree(self.extraction(manifest.build))
        kept = {manifest.build for manifest in manifests[:KEEP]}
        self._collect_images(kept)
        self._collect_reports(kept)

    def _collect_images(self, kept: set[str]) -> None:
        referenced: set[str] = set()
        for build in kept:
            referenced |= referenced_images(self.extraction(build) / RAW)
        for name, file in self.images.files():
            if name in referenced:
                continue
            if file.is_dir():
                shutil.rmtree(file)
            else:
                file.unlink()

    def _collect_reports(self, kept: set[str]) -> None:
        if not self.reports.is_dir():
            return
        for file in self.reports.iterdir():
            match = _REPORT.fullmatch(file.name)
            if match and not {match["old"], match["new"]} <= kept:
                file.unlink()


def referenced_images(raw: Path) -> set[str]:
    """The images a raw layer's canvases name."""
    with closing(sqlite3.connect(f"{raw.as_uri()}?mode=ro", uri=True)) as database:
        return {name for (name,) in database.execute("SELECT name FROM canvas_images")}
