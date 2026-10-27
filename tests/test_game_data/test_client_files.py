"""
The installed client's files, read by `game_data.archive`, extracted, and
built into a catalogue.

Marked `client_files`, so the default run deselects them: they need the MSCW
client's data on disk, at the path `configs/game_data.ini` sets. Run them with
`pytest -m client_files`. Without the config they fail, saying how to set it,
rather than skip. They read only the files, never the running game, and keep
nothing they read.
"""

import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from functools import partial
from pathlib import Path

import pytest

from game_data.archive import (
    ArchiveError,
    BrokenLink,
    CanvasNode,
    ClientData,
    MsPack,
    Pixels,
    PropertyNode,
    WzArchive,
)
from game_data.catalogue import CATALOGUE, SCHEMA_VERSION, Catalogue, build_catalogue
from game_data.config import ClientPathNotSet, client_data_path
from game_data.extraction import Freshness, Store, extract, status

pytestmark = pytest.mark.client_files


@pytest.fixture(scope="module")
def data() -> Path:
    try:
        return client_data_path()
    except (ClientPathNotSet, NotADirectoryError) as error:
        pytest.fail(str(error))


def _archives(data: Path) -> list[Path]:
    """Every `.wz` under `Data`."""
    return sorted(data.rglob("*.wz"))


def _packs(data: Path) -> list[Path]:
    """Every `.ms` in `Data/Packs`."""
    return sorted((data / "Packs").glob("*.ms"))


def _pack_images(pack: MsPack) -> list[str]:
    return [entry.name for entry in pack.entries if entry.name.endswith(".img")]


def test_every_image_in_every_archive_parses(data: Path) -> None:
    failures: list[str] = []
    images = 0
    archives = _archives(data)
    assert archives, f"no .wz archives under {data}"
    for path in archives:
        try:
            archive = WzArchive.open(path)
        except ArchiveError as error:
            failures.append(str(error))
            continue
        for _, entry in archive.images():
            images += 1
            try:
                archive.parse(entry)
            except ArchiveError as error:
                failures.append(str(error))

    assert images > 0
    assert failures == [], f"{len(failures)} of {images} images failed"


def test_every_image_in_every_pack_parses(data: Path) -> None:
    failures: list[str] = []
    images = 0
    packs = _packs(data)
    assert packs, f"no .ms packs in {data / 'Packs'}"
    for path in packs:
        try:
            pack = MsPack.open(path)
        except ArchiveError as error:
            failures.append(str(error))
            continue
        for entry in pack.entries:
            if not entry.name.endswith(".img"):
                continue
            images += 1
            try:
                pack.parse(entry)
            except ArchiveError as error:
                failures.append(str(error))

    assert images > 0
    assert failures == [], f"{len(failures)} of {images} images failed"


def test_the_namespace_reaches_every_image_in_every_archive_and_pack(
    data: Path,
) -> None:
    on_disk = {
        path: len(images)
        for path in _archives(data)
        if (images := WzArchive.open(path).images())
    }
    for path in _packs(data):
        if images := _pack_images(MsPack.open(path)):
            on_disk[path] = len(images)

    reached: dict[Path, int] = {}
    for image in ClientData(data).root.walk():
        reached[image.archive] = reached.get(image.archive, 0) + 1

    assert reached == on_disk


def test_every_canvas_in_every_archive_and_pack_decodes(data: Path) -> None:
    failures: list[str] = []
    canvases = 0
    images: list[tuple[Path, Callable[[], PropertyNode], Callable[..., Pixels]]] = []
    for path in _archives(data):
        archive = WzArchive.open(path)
        images += [
            (path, partial(archive.parse, entry), partial(archive.pixels, entry))
            for _, entry in archive.images()
        ]
    for path in _packs(data):
        pack = MsPack.open(path)
        images += [
            (path, partial(pack.parse, entry), partial(pack.pixels, entry))
            for entry in pack.entries
            if entry.name.endswith(".img")
        ]
    for path, parse, pixels_of in images:
        for node_path, node in parse().walk():
            if not isinstance(node, CanvasNode):
                continue
            canvases += 1
            ref = node.canvas
            try:
                pixels = pixels_of(ref, node_path)
            except ArchiveError as error:
                failures.append(str(error))
                continue
            if pixels.shape != (ref.height, ref.width, 4):
                failures.append(f"{path} {node_path}: {pixels.shape}")

    assert canvases > 0
    assert failures == [], f"{len(failures)} of {canvases} canvases failed"


def test_every_data_side_canvas_reaches_its_pixels(data: Path) -> None:
    """
    Every canvas outside `_Canvas`, through `ClientData.canvas`.

    The one failure allowed is the client's own: a link naming a node its
    archive doesn't have, which `canvas` reports rather than return the 1x1
    placeholder. The PR counts them.
    """
    client = ClientData(data)
    failures: list[str] = []
    canvases = 0
    for image in client.root.walk():
        if "_Canvas" in image.path.split("/"):
            continue
        for node_path, node in client.node(image.path).walk():
            if not isinstance(node, CanvasNode):
                continue
            canvases += 1
            try:
                client.canvas(f"{image.path}/{node_path}")
            except BrokenLink:
                pass
            except ArchiveError as error:
                failures.append(str(error))

    assert canvases > 0
    assert failures == [], f"{len(failures)} of {canvases} canvases failed"


# The slice of the client the extraction check copies: one data tree with its
# `_Canvas` sibling, one with raw data (`Effect`), and the pack whose images
# join the first. About 22 MB, so the check takes seconds. The whole client
# takes about 16 minutes to extract, and is extracted only on demand, with
# `python -m game_data extract`, never by a test.
SLICE_TREES = ("Mob", "Effect")
SLICE_PACKS = ("Mob_00000.ms",)


def test_extracting_a_slice_of_the_client_into_a_temporary_store_completes(
    data: Path, tmp_path: Path
) -> None:
    """
    `SLICE_TREES` and `SLICE_PACKS`, copied as a client of their own, into a
    store under `tmp_path`, never the real one. The only failures it may record
    are links naming nothing (`BrokenLink`). The copy and the store are deleted
    afterwards, pass or fail: pytest keeps recent `tmp_path` folders, and these
    hold the client's data.
    """
    client = tmp_path / "Data"
    root = tmp_path / "store"
    try:
        for tree in SLICE_TREES:
            shutil.copytree(data / tree, client / tree)
        (client / "Packs").mkdir()
        for pack in SLICE_PACKS:
            shutil.copy2(data / "Packs" / pack, client / "Packs" / pack)

        done = extract(client, root)

        manifest = done.manifest
        assert done.created
        assert manifest.images > 0
        assert manifest.canvases > 0
        assert all("names nothing" in f.reason for f in manifest.failures)
        assert status(client, root).freshness is Freshness.FRESH
    finally:
        shutil.rmtree(client, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)


# The slice the catalogue checks extract: every map and what it draws from, and
# the strings that name them. About 140 MB, decoded once for the module.
CATALOGUE_TREES = ("Map", "String")


@pytest.fixture(scope="module")
def map_store(data: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """
    `CATALOGUE_TREES`, copied as a client of their own, extracted with the
    catalogue into a temporary store; the store. Both are deleted afterwards,
    pass or fail, as in the extraction check above.
    """
    base = tmp_path_factory.mktemp("catalogue")
    client = base / "Data"
    root = base / "store"
    try:
        for tree in CATALOGUE_TREES:
            shutil.copytree(data / tree, client / tree)
        extract(client, root, catalogue=build_catalogue)
        yield root
    finally:
        shutil.rmtree(client, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)


def _count(root: Path, sql: str) -> int:
    manifest = Store(root).latest()
    assert manifest is not None
    file = Store(root).extraction(manifest.build) / CATALOGUE
    with closing(sqlite3.connect(file)) as database:
        return database.execute(sql).fetchone()[0]


def test_the_catalogue_builds_from_the_clients_maps_and_strings(
    map_store: Path,
) -> None:
    manifest = Store(map_store).latest()

    assert manifest is not None
    assert manifest.catalogue_schema_version == SCHEMA_VERSION
    for table in (
        "strings",
        "maps",
        "footholds",
        "ropes",
        "portals",
        "spawns",
        "map_layers",
        "layer_frames",
        "physics",
    ):
        assert _count(map_store, f"SELECT count(*) FROM {table}") > 0, table


def test_every_map_image_is_a_map_with_vr_bounds_given_or_derived(
    data: Path, map_store: Path, record_property: Callable[[str, object], None]
) -> None:
    """The PR counts the derived bounds and the maps with no minimap."""
    images = sum(
        len(ClientData(data).directory(f"Map/Map/{folder}").images)
        for folder in ClientData(data).directory("Map/Map").directories
    )

    assert _count(map_store, "SELECT count(*) FROM maps") == images
    assert _count(map_store, "SELECT count(*) FROM maps WHERE vr_left IS NULL") == 0
    record_property(
        "vr_derived", _count(map_store, "SELECT count(*) FROM maps WHERE vr_derived")
    )
    record_property(
        "no_minimap",
        _count(map_store, "SELECT count(*) FROM maps WHERE minimap_mag IS NULL"),
    )


def test_a_known_town_is_found_by_name(map_store: Path) -> None:
    with Catalogue.latest(map_store) as cat:
        henesys = cat.map("Henesys")

    assert henesys.town
    assert henesys.name == "Henesys"
    assert henesys.footholds
