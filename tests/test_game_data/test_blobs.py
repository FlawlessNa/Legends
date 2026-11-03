"""
The client font's blobs: written by `extract`, backfilled on a Build the store
already has, and kept or deleted by retention. A synthetic client whose
`UI/Font/` holds a raw-data node, into a temporary store.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from game_data.archive.client import Image
from game_data.extraction import Store, extract
from tests.test_game_data import wz_writer as w

LUT = b"\x00\x01" * 8


def font(version: int) -> bytes:
    return bytes([version]) * 40


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_client(data: Path, version: int = 1) -> Path:
    w.write_tree(
        data / "UI",
        [
            w.Dir(
                "Font",
                [
                    w.Img(
                        "Noto.img",
                        [w.RawData("FONT_DATA", font(version)), w.Int("v", version)],
                    )
                ],
            ),
            w.Img("StatusBar.img", [w.Int("v", version)]),
        ],
        ini=False,
    )
    w.write_tree(data / "Etc", [w.Img("lut.img", [w.RawData("4", LUT)])], ini=False)
    return data


class Clock:
    def __init__(self) -> None:
        self.time = datetime(2026, 10, 31, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.time += timedelta(seconds=1)
        return self.time


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "store"


def blobs(root: Path) -> dict[str, bytes]:
    folder = root / "blobs"
    if not folder.is_dir():
        return {}
    return {file.name: file.read_bytes() for file in sorted(folder.iterdir())}


def test_extract_writes_the_bytes_of_every_font_raw_data_to_blobs_by_sha256(
    tmp_path: Path, root: Path
) -> None:
    extract(write_client(tmp_path / "Data"), root)

    assert blobs(root) == {sha(font(1)): font(1)}


def test_raw_data_outside_the_font_folder_is_not_written(
    tmp_path: Path, root: Path
) -> None:
    extract(write_client(tmp_path / "Data"), root)

    assert sha(LUT) not in blobs(root)


def test_a_build_already_extracted_gets_its_missing_blobs_from_the_font_image_only(
    tmp_path: Path, root: Path, mocker: MockerFixture
) -> None:
    client = write_client(tmp_path / "Data")
    first = extract(client, root)
    raw = root / "extractions" / first.manifest.build / "raw.sqlite"
    before = raw.read_bytes()
    for file in (root / "blobs").iterdir():
        file.unlink()
    parse = mocker.spy(Image, "parse")

    again = extract(client, root)

    assert not again.created
    assert blobs(root) == {sha(font(1)): font(1)}
    assert [call.args[0].path for call in parse.call_args_list] == ["UI/Font/Noto.img"]
    assert raw.read_bytes() == before
    assert again.manifest.extractor_version == first.manifest.extractor_version


def test_a_build_with_all_its_blobs_is_not_read_again(
    tmp_path: Path, root: Path, mocker: MockerFixture
) -> None:
    client = write_client(tmp_path / "Data")
    extract(client, root)
    parse = mocker.spy(Image, "parse")

    extract(client, root)

    assert parse.call_count == 0


def test_a_store_extracted_before_blobs_existed_gains_them(
    tmp_path: Path, root: Path
) -> None:
    client = write_client(tmp_path / "Data")
    extract(client, root)
    (root / "blobs" / sha(font(1))).unlink()
    (root / "blobs").rmdir()

    extract(client, root)

    assert blobs(root) == {sha(font(1)): font(1)}


def test_retention_keeps_the_blobs_the_kept_extractions_name_and_deletes_the_rest(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    for version in (1, 2):
        extract(
            write_client(tmp_path / str(version) / "Data", version), root, now=clock
        )
    assert set(blobs(root)) == {sha(font(1)), sha(font(2))}
    (root / "blobs" / "stray.tmp").write_bytes(b"left by a dead run")
    (root / "blobs" / ("ab" * 32)).write_bytes(b"named by nobody")

    extract(write_client(tmp_path / "3" / "Data", 3), root, now=clock)

    kept = {m.build for m in Store(root).manifests()}
    assert len(kept) == 2
    assert blobs(root) == {sha(font(2)): font(2), sha(font(3)): font(3)}


def test_a_blob_two_kept_extractions_share_survives_the_oldest_going(
    tmp_path: Path, root: Path, clock: Clock
) -> None:
    same = write_client(tmp_path / "a" / "Data", 1)
    extract(same, root, now=clock)
    other = write_client(tmp_path / "b" / "Data", 1)
    w.write_tree(other / "Etc", [w.Img("other.img", [w.Int("x", 1)])], ini=False)
    extract(other, root, now=clock)

    extract(write_client(tmp_path / "c" / "Data", 2), root, now=clock)

    assert sha(font(1)) in blobs(root)
    assert len(Store(root).manifests()) == 2
