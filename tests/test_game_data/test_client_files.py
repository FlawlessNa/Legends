"""
The installed client's files, read by `game_data.archive`, extracted, and
built into a catalogue.

Marked `client_files`, so the default run deselects them: they need the MSCW
client's data on disk, at the path `configs/game_data.ini` sets. Run them with
`pytest -m client_files`. Without the config they fail, saying how to set it,
rather than skip. They read only the files, never the running game, and keep
nothing they read.
"""

import hashlib
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
from game_data.render import render_map
from game_data.sprites import Sprites

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


# The slice the catalogue checks extract: every map and what it draws from, the
# strings that name them, every mob and skill with the packs that hold them,
# and the character's body, whose actions time the skills: `Character`'s own
# archives and its `_Canvas`, not the equipment beside them. About 280 MB,
# decoded once for the module, in several minutes.
CATALOGUE_TREES = ("Map", "String", "Mob", "Skill")
CATALOGUE_PACKS = ("Mob_00000.ms", "Skill_00000.ms")
BODY = "Character"


@pytest.fixture(scope="module")
def catalogue_store(
    data: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Path]:
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
        (client / "Packs").mkdir()
        for pack in CATALOGUE_PACKS:
            shutil.copy2(data / "Packs" / pack, client / "Packs" / pack)
        shutil.copytree(data / BODY / "_Canvas", client / BODY / "_Canvas")
        for file in (data / BODY).iterdir():
            if file.is_file():
                shutil.copy2(file, client / BODY / file.name)
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


def test_the_catalogue_builds_from_the_clients_maps_mobs_skills_and_strings(
    catalogue_store: Path,
) -> None:
    manifest = Store(catalogue_store).latest()

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
        "mobs",
        "mob_frames",
        "skills",
        "skill_levels",
        "actions",
    ):
        assert _count(catalogue_store, f"SELECT count(*) FROM {table}") > 0, table


def test_every_map_image_is_a_map_with_vr_bounds_given_or_derived(
    data: Path, catalogue_store: Path, record_property: Callable[[str, object], None]
) -> None:
    """The PR counts the derived bounds and the maps with no minimap."""
    images = sum(
        len(ClientData(data).directory(f"Map/Map/{folder}").images)
        for folder in ClientData(data).directory("Map/Map").directories
    )

    assert _count(catalogue_store, "SELECT count(*) FROM maps") == images
    assert (
        _count(catalogue_store, "SELECT count(*) FROM maps WHERE vr_left IS NULL") == 0
    )
    record_property(
        "vr_derived",
        _count(catalogue_store, "SELECT count(*) FROM maps WHERE vr_derived"),
    )
    record_property(
        "no_minimap",
        _count(catalogue_store, "SELECT count(*) FROM maps WHERE minimap_mag IS NULL"),
    )


def test_a_known_town_is_found_by_name(catalogue_store: Path) -> None:
    with Catalogue.latest(catalogue_store) as cat:
        henesys = cat.map("Henesys")

    assert henesys.town
    assert henesys.name == "Henesys"
    assert henesys.footholds


def test_swing_o1_takes_800_ms(catalogue_store: Path) -> None:
    with Catalogue.latest(catalogue_store) as cat:
        assert cat.action_duration("swingO1") == 800


def test_magic_claw_takes_800_ms_and_costs_mp_at_every_level(
    catalogue_store: Path,
) -> None:
    """800 ms is `animation_time=0.8` in `maple/model/characters/magicians.py`."""
    with Catalogue.latest(catalogue_store) as cat:
        claw = cat.skill("Magic Claw")
        duration = cat.skill_duration("Magic Claw")

    assert duration == 800
    assert claw.levels
    assert len(claw.levels) == claw.max_level
    assert all(level.mp_con is not None for level in claw.levels)


def test_snail_is_found_by_name_with_its_frames(catalogue_store: Path) -> None:
    with Catalogue.latest(catalogue_store) as cat:
        snail = cat.mob("Snail")
        spawning = cat.maps_spawning("Snail")

    assert snail.name == "Snail"
    assert snail.frames
    assert spawning


def test_every_mob_and_skill_image_is_in_the_catalogue(
    data: Path, catalogue_store: Path, record_property: Callable[[str, object], None]
) -> None:
    """The PR counts the linked mobs, the skills and their levels."""
    client = ClientData(data)
    mob_images = [name for name in client.directory("Mob").images if name[0].isdigit()]
    job_images = [
        name for name in client.directory("Skill").images if name[:-4].isdigit()
    ]

    assert _count(catalogue_store, "SELECT count(*) FROM mobs") == len(mob_images)
    assert _count(catalogue_store, "SELECT count(DISTINCT job) FROM skills") == len(
        job_images
    )
    assert (
        _count(
            catalogue_store,
            "SELECT count(*) FROM mobs WHERE link IS NOT NULL AND id NOT IN "
            "(SELECT mob FROM mob_frames)",
        )
        == 0
    )
    for name, sql in {
        "mobs_linked": "SELECT count(*) FROM mobs WHERE link IS NOT NULL",
        "skills": "SELECT count(*) FROM skills",
        "skill_levels": "SELECT count(*) FROM skill_levels",
        "actions": "SELECT count(DISTINCT action) FROM actions",
    }.items():
        record_property(name, _count(catalogue_store, sql))


# --- render ------------------------------------------------------------------


def test_a_town_renders_whole_with_its_overlays_and_hitboxes(
    catalogue_store: Path,
) -> None:
    with Catalogue.latest(catalogue_store) as cat:
        henesys = cat.map("Henesys")
        screen = render_map(cat, henesys.id, overlays=True, hitboxes=True)

    vr = henesys.vr
    assert screen.shape == (vr.bottom - vr.top, vr.right - vr.left, 4)
    assert screen[..., 3].any()


def test_every_map_renders(
    catalogue_store: Path, record_property: Callable[[str, object], None]
) -> None:
    """Each map is drawn at a quarter size, its spawns and hitboxes included."""
    manifest = Store(catalogue_store).latest()
    assert manifest is not None
    file = Store(catalogue_store).extraction(manifest.build) / CATALOGUE
    with closing(sqlite3.connect(file)) as database:
        map_ids = [
            row[0] for row in database.execute("SELECT id FROM maps ORDER BY id")
        ]
    rendered = 0
    with Catalogue.latest(catalogue_store) as cat:
        for map_id in map_ids:
            screen = render_map(cat, map_id, scale=0.25, hitboxes=True)
            assert screen.ndim == 3, map_id
            rendered += 1

    assert rendered > 0
    record_property("maps_rendered", rendered)


def test_the_backgrounds_the_reading_of_rx_moves_are_counted(
    catalogue_store: Path, record_property: Callable[[str, object], None]
) -> None:
    """
    The PR counts, never lists, the backgrounds `STORED_AT_RX` decides for: the
    two readings place every background a camera's centre apart, which shows
    on any axis it doesn't tile along.
    """
    drawn = "kind = 'back' AND asset IS NOT NULL"
    for name, where in {
        "backgrounds": drawn,
        "backgrounds_still_rx_ry_0": f"{drawn} AND type = 0 AND rx = 0 AND ry = 0",
        "backgrounds_rx_ry_0": f"{drawn} AND rx = 0 AND ry = 0",
        "backgrounds_untiled_on_an_axis": f"{drawn} AND type NOT IN (3, 6, 7)",
    }.items():
        record_property(
            name,
            _count(catalogue_store, f"SELECT count(*) FROM map_layers WHERE {where}"),
        )
    record_property(
        "maps_with_still_rx_ry_0",
        _count(
            catalogue_store,
            "SELECT count(DISTINCT map) FROM map_layers WHERE "
            f"{drawn} AND type = 0 AND rx = 0 AND ry = 0",
        ),
    )


def test_the_status_bars_digit_and_the_font_come_out_of_a_slice_of_ui(
    data: Path, tmp_path: Path
) -> None:
    """
    Extracts `UI` alone into a temporary store, never the real one, and reads
    the status bar's 5x7 digit and the client font's bytes back through
    `Sprites`. `python -m game_data extract` leaves the same one
    6,188,880-byte file in the real store's `blobs/`.
    """
    client = tmp_path / "Data"
    root = tmp_path / "store"
    try:
        shutil.copytree(data / "UI", client / "UI")
        extract(client, root)

        with Sprites.latest(root) as sprites:
            digit = sprites.canvas("UI/StatusBar.img/gauge/number/0")
            font = sprites.raw_data("UI/Font/NotoSansKRMedium.img/FONT_DATA")

        assert digit.rgba.shape == (7, 5, 4)
        assert len(font) == 6_188_880
        assert [file.name for file in (root / "blobs").iterdir()] == [
            hashlib.sha256(font).hexdigest()
        ]
    finally:
        shutil.rmtree(client, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)
