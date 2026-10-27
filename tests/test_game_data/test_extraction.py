"""
`extract` and `status` against a synthetic client, into a temporary store.

The fixture client has what extraction must handle: a data tree whose
canvases are placeholders linking into its `_Canvas` sibling, a pack whose
canvases carry `_hash`, a sound, raw data, and a canvas whose link names
nothing. `write_client(data, version)` writes it; another `version` changes
one value and one canvas's pixels, so it's another Build.
"""

import hashlib
import json
import os
import sqlite3
import zlib
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture

from game_data.archive import ArchiveError, ms, wz
from game_data.extraction import (
    EXTRACTOR_VERSION,
    Freshness,
    ImageStore,
    Store,
    extract,
    status,
)
from game_data.extraction.build import file_sha256
from tests.test_game_data import wz_writer as w

PACK_HASH = "cd" * 32


def bgra(pixels: list[tuple[int, int, int, int]]) -> bytes:
    return zlib.compress(b"".join(bytes([b, g, r, a]) for r, g, b, a in pixels))


def stand_pixels(version: int) -> list[tuple[int, int, int, int]]:
    return [(version, 2, 3, 255), (4, 5, 6, 255), (7, 8, 9, 255), (10, 11, 12, 255)]


OWN = [(10, 20, 30, 40), (50, 60, 70, 80)]
PACK = [(1, 1, 1, 1)]


def placeholder(name: str, *children: w.Property) -> w.Canvas:
    return w.Canvas(name, 1, 1, bgra([(255, 0, 255, 255)]), format=2, children=children)


def mob_info(level: int) -> w.Prop:
    """A mob's `info`, with the stats every mob has, which the catalogue reads."""
    stats = ("maxHP", "maxMP", "PADamage", "MADamage", "PDDamage", "MDDamage")
    return w.Prop(
        "info",
        [
            w.Int("level", level),
            w.Short("speed", -10),
            *(w.Int(key, 1) for key in (*stats, "acc", "eva", "pushed")),
        ],
    )


def write_client(data: Path, version: int = 1) -> Path:
    w.write_tree(
        data / "Mob",
        [
            w.Dir("_Canvas"),
            w.Img(
                "0100100.img",
                [
                    mob_info(version),
                    w.Prop(
                        "stand",
                        [
                            placeholder(
                                "0",
                                w.Vector("origin", 1, 2),
                                w.String("_outlink", "Mob/_Canvas/0100100.img/stand/0"),
                            ),
                            placeholder("1", w.String("_inlink", "stand/0")),
                            w.Canvas("2", 2, 1, bgra(OWN), format=2),
                            w.Uol("3", "0"),
                            placeholder("broken", w.String("_inlink", "stand/none")),
                        ],
                    ),
                ],
            ),
        ],
        ini=False,
    )
    w.write_tree(
        data / "Mob" / "_Canvas",
        [
            w.Img(
                "0100100.img",
                [
                    w.Prop(
                        "stand",
                        [w.Canvas("0", 2, 2, bgra(stand_pixels(version)), format=2)],
                    )
                ],
            )
        ],
        ini=False,
    )
    w.write_tree(
        data / "Sound",
        [w.Img("Bgm00.img", [w.Sound("FloralLife", b"\x01\x02\x03" * 10, 1500)])],
        ini=False,
    )
    w.write_tree(
        data / "Etc",
        [
            w.Img(
                "lut.img",
                [
                    w.RawData("4", b"\x00\x01" * 8),
                    w.Convex("shape", [(1, 2), (3, 4)]),
                    w.Long("long", 2**40),
                    w.Float("float", 0.5),
                    w.Double("double", 2.0),
                    w.Null("null"),
                ],
            )
        ],
        ini=False,
    )
    w.write_pack(
        data / "Packs" / "Mob_00000.ms",
        [
            w.Img(
                "Mob/0100200.img",
                [
                    mob_info(1),
                    w.Prop(
                        "stand",
                        [
                            w.Canvas(
                                "0",
                                1,
                                1,
                                bgra(PACK),
                                format=2,
                                children=[w.String("_hash", PACK_HASH)],
                            )
                        ],
                    ),
                ],
            )
        ],
    )
    return data


@pytest.fixture
def client(tmp_path: Path) -> Path:
    return write_client(tmp_path / "Data")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "store"


class Clock:
    """A clock that moves a second each time it's read."""

    def __init__(self) -> None:
        self.time = datetime(2026, 10, 26, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.time += timedelta(seconds=1)
        return self.time


@pytest.fixture
def clock() -> Clock:
    return Clock()


def trees(root: Path, build: str) -> dict[str, tuple[str, Any]]:
    raw = root / "extractions" / build / "raw.sqlite"
    with closing(sqlite3.connect(raw)) as database:
        rows = database.execute("SELECT path, sha256, tree FROM images").fetchall()
    return {path: (sha256, json.loads(tree)) for path, sha256, tree in rows}


def files(root: Path) -> dict[str, bytes]:
    """Every file under `root`, with its bytes."""
    return {
        file.relative_to(root).as_posix(): file.read_bytes()
        for file in sorted(root.rglob("*"))
        if file.is_file()
    }


def latest(root: Path) -> str | None:
    manifest = Store(root).latest()
    return manifest.build if manifest else None


def builds(root: Path) -> set[str]:
    return {folder.name for folder in (root / "extractions").iterdir()}


def rgba(pixels: list[tuple[int, int, int, int]], width: int) -> np.ndarray:
    return np.array(pixels, dtype=np.uint8).reshape(-1, width, 4)


def read_png(file: Path) -> np.ndarray:
    import cv2

    image = cv2.imread(str(file), cv2.IMREAD_UNCHANGED)
    assert image is not None
    return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)


# --- one extraction ----------------------------------------------------------


def test_the_manifest_records_the_build_and_every_archive(
    client: Path, root: Path, clock: Clock
) -> None:
    done = extract(client, root, now=clock)

    manifest = json.loads(
        (root / "extractions" / done.manifest.build / "manifest.json").read_text()
    )
    assert manifest["build"] == done.manifest.build
    assert manifest["extractor_version"] == EXTRACTOR_VERSION
    assert manifest["catalogue_schema_version"] is None
    assert manifest["extracted_at"] == clock.time.isoformat(timespec="microseconds")
    archives = sorted(
        [*client.rglob("*.wz"), *(client / "Packs").glob("*.ms")],
        key=lambda file: file.relative_to(client).as_posix(),
    )
    assert manifest["archives"] == {
        file.relative_to(client).as_posix(): {
            "size": file.stat().st_size,
            "mtime_ns": file.stat().st_mtime_ns,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
        for file in archives
    }
    assert len(manifest["archives"]) == 5
    assert (manifest["images"], manifest["canvases"]) == (5, 6)


def test_raw_holds_every_image_with_the_sha256_of_its_tree(
    client: Path, root: Path
) -> None:
    done = extract(client, root)

    stored = trees(root, done.manifest.build)
    assert set(stored) == {
        "Mob/0100100.img",
        "Mob/_Canvas/0100100.img",
        "Mob/0100200.img",
        "Sound/Bgm00.img",
        "Etc/lut.img",
    }
    raw = root / "extractions" / done.manifest.build / "raw.sqlite"
    with closing(sqlite3.connect(raw)) as database:
        for path, sha256, tree in database.execute("SELECT * FROM images"):
            assert sha256 == hashlib.sha256(tree.encode()).hexdigest(), path


def test_a_placeholder_is_the_image_its_link_leads_to_with_its_own_properties(
    client: Path, root: Path
) -> None:
    done = extract(client, root)

    stand = trees(root, done.manifest.build)["Mob/0100100.img"][1]["stand"]
    assert isinstance(stand, dict)
    image = ImageStore(root / "images")
    linked = stand["0"]
    assert linked == {
        "$type": "canvas",
        "image": linked["image"],
        "w": 2,
        "h": 2,
        "origin": {"$type": "vector", "x": 1, "y": 2},
        "_outlink": "Mob/_Canvas/0100100.img/stand/0",
    }
    np.testing.assert_array_equal(
        read_png(image.path(linked["image"])), rgba(stand_pixels(1), 2)
    )
    assert stand["1"]["image"] == linked["image"]
    assert stand["3"] == {"$type": "uol", "path": "0"}
    own = stand["2"]
    np.testing.assert_array_equal(read_png(image.path(own["image"])), rgba(OWN, 2))


def test_the_canvas_archives_own_canvas_is_the_same_image(
    client: Path, root: Path
) -> None:
    done = extract(client, root)

    stored = trees(root, done.manifest.build)
    data_side = stored["Mob/0100100.img"][1]["stand"]["0"]["image"]
    canvas_side = stored["Mob/_Canvas/0100100.img"][1]["stand"]["0"]["image"]
    assert data_side == canvas_side


def test_a_canvas_with_a_hash_is_named_by_it(client: Path, root: Path) -> None:
    done = extract(client, root)

    canvas = trees(root, done.manifest.build)["Mob/0100200.img"][1]["stand"]["0"]
    assert canvas["image"] == PACK_HASH
    assert canvas["_hash"] == PACK_HASH
    np.testing.assert_array_equal(
        read_png(ImageStore(root / "images").path(PACK_HASH)), rgba(PACK, 1)
    )


def test_sounds_and_raw_data_are_references_with_their_bytes_hash(
    client: Path, root: Path
) -> None:
    done = extract(client, root)

    stored = trees(root, done.manifest.build)
    assert stored["Sound/Bgm00.img"][1]["FloralLife"] == {
        "$type": "sound",
        "duration_ms": 1500,
        "length": 30,
        "sha256": hashlib.sha256(b"\x01\x02\x03" * 10).hexdigest(),
    }
    lut = stored["Etc/lut.img"][1]
    assert lut["4"] == {
        "$type": "raw_data",
        "length": 16,
        "sha256": hashlib.sha256(b"\x00\x01" * 8).hexdigest(),
    }
    assert lut["shape"] == {
        "$type": "convex",
        "0": {"$type": "vector", "x": 1, "y": 2},
        "1": {"$type": "vector", "x": 3, "y": 4},
    }


def test_each_canvas_is_decoded_once(
    client: Path, root: Path, mocker: MockerFixture
) -> None:
    in_wz = mocker.spy(wz, "decode_canvas")
    in_pack = mocker.spy(ms, "decode_canvas")

    done = extract(client, root)

    # Three sources of pixels: `_Canvas` stand/0, which stand/0, stand/1 and
    # the `_Canvas` image's own canvas all lead to; stand/2; and the pack's.
    assert in_wz.call_count == 2
    assert in_pack.call_count == 1
    assert done.written == 3
    assert len(list((root / "images").rglob("*.png"))) == 3


def test_a_link_naming_nothing_is_a_recorded_failure_and_extraction_carries_on(
    client: Path, root: Path
) -> None:
    done = extract(client, root)

    assert done.created
    (failure,) = done.manifest.failures
    assert (failure.image, failure.node) == ("Mob/0100100.img", "stand/broken")
    assert "stand/broken/_inlink" in failure.reason
    assert "names nothing" in failure.reason
    manifest = json.loads(
        (root / "extractions" / done.manifest.build / "manifest.json").read_text()
    )
    assert manifest["failures"] == [
        {"image": failure.image, "node": failure.node, "reason": failure.reason}
    ]
    broken = trees(root, done.manifest.build)["Mob/0100100.img"][1]["stand"]["broken"]
    assert broken["image"] is None
    assert (broken["w"], broken["h"]) == (1, 1)


# --- the same build again ---------------------------------------------------


def test_extracting_the_same_client_twice_gives_one_extraction(
    client: Path, root: Path, clock: Clock
) -> None:
    first = extract(client, root, now=clock)
    images = files(root / "images")
    raw = (root / "extractions" / first.manifest.build / "raw.sqlite").read_bytes()

    second = extract(client, root, now=clock)

    assert not second.created
    assert second.manifest.build == first.manifest.build
    assert builds(root) == {first.manifest.build}
    assert files(root / "images") == images
    assert (
        root / "extractions" / first.manifest.build / "raw.sqlite"
    ).read_bytes() == raw
    assert second.manifest.extracted_at > first.manifest.extracted_at
    assert Store(root).latest() == second.manifest


def test_the_build_id_ignores_where_the_client_is_and_its_times(
    tmp_path: Path, root: Path
) -> None:
    first = write_client(tmp_path / "a" / "Data")
    second = write_client(tmp_path / "b" / "Data")
    for file in second.rglob("*.wz"):
        os.utime(file, ns=(10**18, 10**18))

    assert extract(first, root).manifest.build == extract(second, root).manifest.build
    assert len(builds(root)) == 1


def test_re_extracting_a_kept_older_build_makes_it_the_latest(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    a = extract(write_client(tmp_path / "a" / "Data", 1), root, now=clock)
    b = extract(write_client(tmp_path / "b" / "Data", 2), root, now=clock)
    assert latest(root) == b.manifest.build

    again = extract(tmp_path / "a" / "Data", root, now=clock)

    assert not again.created
    assert builds(root) == {a.manifest.build, b.manifest.build}
    assert latest(root) == a.manifest.build


# --- retention ------------------------------------------------------------------


def test_after_a_third_build_only_the_two_latest_and_their_images_remain(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    done = [
        extract(write_client(tmp_path / str(v) / "Data", v), root, now=clock)
        for v in (1, 2)
    ]
    reports = root / "reports"
    reports.mkdir()
    one, two = (d.manifest.build for d in done)
    (reports / f"{one}__{two}.html").write_text("1 to 2")
    oldest_image = trees(root, one)["Mob/_Canvas/0100100.img"][1]["stand"]["0"]["image"]
    assert ImageStore(root / "images").has(oldest_image)

    three = extract(write_client(tmp_path / "3" / "Data", 3), root, now=clock)
    (reports / f"{two}__{three.manifest.build}.html").write_text("2 to 3")
    extract(tmp_path / "3" / "Data", root, now=clock)

    assert builds(root) == {two, three.manifest.build}
    assert not ImageStore(root / "images").has(oldest_image)
    kept: set[str] = set()
    for build in builds(root):
        with closing(
            sqlite3.connect(root / "extractions" / build / "raw.sqlite")
        ) as db:
            kept |= {name for (name,) in db.execute("SELECT name FROM canvas_images")}
    on_disk = {file.stem for file in (root / "images").rglob("*.png")}
    assert on_disk == kept
    assert sorted(file.name for file in reports.iterdir()) == [
        f"{two}__{three.manifest.build}.html"
    ]


# --- failures -------------------------------------------------------------------


def test_a_failed_extraction_leaves_the_store_byte_identical(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    extract(write_client(tmp_path / "a" / "Data", 1), root, now=clock)
    before = files(root)
    broken = write_client(tmp_path / "b" / "Data", 2)
    w.write_tree(broken / "Etc", [w.Img("lut.img", [w.Bad("oops")])], ini=False)

    with pytest.raises(ArchiveError, match="lut.img"):
        extract(broken, root, now=clock)

    after = files(root)
    assert {path: after[path] for path in before} == before
    new = set(after) - set(before)
    assert all(path.startswith("images/") for path in new)
    assert {f.name for f in (root / "extractions").iterdir()} == set(builds(root))
    assert not any(f.name.startswith(".") for f in (root / "extractions").iterdir())


def test_images_a_failed_run_wrote_go_at_the_next_successful_extraction(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    def failing(extraction: Path, images: ImageStore) -> int | None:
        raise RuntimeError("the catalogue failed")

    first = write_client(tmp_path / "a" / "Data", 1)
    extract(first, root, now=clock)
    kept = files(root / "images")

    with pytest.raises(RuntimeError):
        extract(write_client(tmp_path / "b" / "Data", 2), root, catalogue=failing)
    assert set(files(root / "images")) > set(kept)

    extract(first, root, now=clock)

    assert files(root / "images") == kept


# --- hooks -----------------------------------------------------------------------


def test_the_catalogue_hook_runs_on_the_new_extraction_before_it_lands(
    client: Path, root: Path
) -> None:
    seen: list[tuple[Path, bool, bool]] = []

    def catalogue(extraction: Path, images: ImageStore) -> int | None:
        seen.append(
            (extraction, (extraction / "raw.sqlite").is_file(), images.folder.is_dir())
        )
        return 7

    done = extract(client, root, catalogue=catalogue)

    ((folder, had_raw, had_images),) = seen
    assert folder.parent == root / "extractions"
    assert folder.name.startswith(".")
    assert had_raw
    assert had_images
    assert done.manifest.catalogue_schema_version == 7


def test_the_report_hook_runs_when_a_new_build_lands_after_another(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    calls: list[tuple[str, str]] = []

    def report(store: Store, old: str, new: str) -> Path | None:
        calls.append((old, new))
        return store.reports / f"{old}__{new}.html"

    a = extract(
        write_client(tmp_path / "a" / "Data", 1), root, report=report, now=clock
    )
    b = extract(
        write_client(tmp_path / "b" / "Data", 2), root, report=report, now=clock
    )
    extract(tmp_path / "b" / "Data", root, report=report, now=clock)

    assert calls == [(a.manifest.build, b.manifest.build)]
    assert a.report is None
    assert b.report == root / "reports" / f"{a.manifest.build}__{b.manifest.build}.html"


# --- status -------------------------------------------------------------------------


def test_status_is_missing_then_fresh_then_stale(
    client: Path, root: Path, tmp_path: Path
) -> None:
    assert status(client, root).freshness is Freshness.MISSING

    built = extract(client, root).manifest.build
    assert status(client, root).freshness is Freshness.FRESH
    assert status(client, root).latest == built

    w.write_tree(client / "Etc", [w.Img("lut.img", [w.Int("changed", 1)])], ini=False)
    found = status(client, root)
    assert found.freshness is Freshness.STALE
    assert found.changed == ("Etc/Etc.wz",)


def test_an_unchanged_client_is_answered_without_reading_any_archive(
    client: Path, root: Path, mocker: MockerFixture
) -> None:
    extract(client, root)
    read = mocker.patch(
        "game_data.extraction.status.file_sha256",
        side_effect=AssertionError("an archive was read"),
    )

    assert status(client, root).freshness is Freshness.FRESH
    read.assert_not_called()


def test_a_touched_archive_is_read_to_find_it_unchanged(
    client: Path, root: Path, mocker: MockerFixture
) -> None:
    extract(client, root)
    touched = client / "Sound" / "Sound.wz"
    os.utime(touched, ns=(10**18, 10**18))
    read = mocker.patch(
        "game_data.extraction.status.file_sha256", side_effect=file_sha256
    )

    assert status(client, root).freshness is Freshness.FRESH
    read.assert_called_once_with(touched)


def test_an_added_or_removed_archive_is_stale(client: Path, root: Path) -> None:
    extract(client, root)
    w.write_tree(client / "Npc", [w.Img("1.img", [w.Int("a", 1)])], ini=False)
    (client / "Packs" / "Mob_00000.ms").unlink()

    found = status(client, root)

    assert found.freshness is Freshness.STALE
    assert found.changed == ("Npc/Npc.wz", "Packs/Mob_00000.ms")


def test_status_compares_with_the_latest_extraction(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    a = write_client(tmp_path / "a" / "Data", 1)
    b = write_client(tmp_path / "b" / "Data", 2)
    extract(a, root, now=clock)
    extract(b, root, now=clock)

    assert status(a, root).freshness is Freshness.STALE
    assert status(b, root).freshness is Freshness.FRESH
