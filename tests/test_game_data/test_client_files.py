"""
The installed client's files, read by `game_data.archive`.

Marked `client_files`, so the default run deselects them: they need the MSCW
client's data on disk, at the path `configs/game_data.ini` sets. Run them with
`pytest -m client_files`. Without the config they fail, saying how to set it,
rather than skip. They read only the files, never the running game, and keep
nothing they read.
"""

from pathlib import Path

import pytest

from game_data.archive import ArchiveError, ClientData, WzArchive
from game_data.config import ClientPathNotSet, client_data_path

pytestmark = pytest.mark.client_files


@pytest.fixture(scope="module")
def data() -> Path:
    try:
        return client_data_path()
    except (ClientPathNotSet, NotADirectoryError) as error:
        pytest.fail(str(error))


def _archives(data: Path) -> list[Path]:
    """Every `.wz` under `Data`. Packs (`.ms`) are #261's."""
    return sorted(data.rglob("*.wz"))


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


def test_the_namespace_reaches_every_image_in_every_archive(data: Path) -> None:
    on_disk = {
        path: len(images)
        for path in _archives(data)
        if (images := WzArchive.open(path).images())
    }

    reached: dict[Path, int] = {}
    for image in ClientData(data).root.walk():
        reached[image.archive] = reached.get(image.archive, 0) + 1

    assert reached == on_disk
