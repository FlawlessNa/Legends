"""
`write_report`: the patch report from one extraction to another, written into
the store as `reports/<old>__<new>.html`.

It is the report hook `extract` calls once a new Build lands and an older
extraction exists, and what `report [OLD NEW]` calls on demand. Both extractions
must be in the store: it reads their raw layers and their catalogues (rebuilt
first if outdated, without the client) and the images the sprites are drawn
from. The page is written to a temporary file and renamed, so a report is never
half there.
"""

import os
from pathlib import Path

from game_data.catalogue import Catalogue
from game_data.extraction import RAW, ExtractionError, Manifest, Store

from .diff import diff_raw
from .page import render
from .summary import summarize


def report_path(store: Store, old: str, new: str) -> Path:
    """Where the report from `old` to `new` is, or would be."""
    return store.reports / f"{old}__{new}.html"


def write_report(store: Store, old: str, new: str) -> Path:
    """
    Writes the report from the extraction of build `old` to that of `new`.

    :return: The report's path.
    :raises ExtractionError: The store lacks either extraction.
    :raises CatalogueError: Either one's raw layer isn't as expected.
    """
    before = _manifest(store, old)
    after = _manifest(store, new)
    raw = diff_raw(
        store.extraction(old) / RAW,
        store.extraction(new) / RAW,
    )
    with (
        Catalogue.open(old, store.root) as old_catalogue,
        Catalogue.open(new, store.root) as new_catalogue,
    ):
        summary = summarize(old_catalogue, new_catalogue)
    page = render(before, after, raw, summary, store.images)
    target = report_path(store, old, new)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(page, encoding="utf-8")
    os.replace(temporary, target)
    return target


def _manifest(store: Store, build: str) -> Manifest:
    try:
        return Manifest.read(store.extraction(build))
    except ExtractionError as error:
        raise ExtractionError(
            f"{store.root} has no extraction {build}; it has "
            + (", ".join(m.build for m in store.manifests()) or "none")
        ) from error
