"""
`python -m game_data extract`, `status`, `show` and `search`, through
`cli.main`, against the synthetic clients of `test_extraction` and
`test_catalogue`.
"""

import json
from pathlib import Path

import pytest

from game_data.catalogue import SCHEMA_VERSION
from game_data.cli import main
from game_data.config import ClientPathNotSet
from game_data.extraction import Manifest
from game_data.extraction.store import referenced_images
from tests.test_game_data.test_catalogue import write_map_client
from tests.test_game_data.test_extraction import write_client


@pytest.fixture
def client(tmp_path: Path) -> Path:
    return write_client(tmp_path / "Data")


def test_extract_says_what_it_did_and_counts_the_failures(
    client: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "store"

    code = main(["extract", "--client", str(client), "--root", str(root)])

    out = capsys.readouterr().out
    assert code == 0
    assert "5 images, 6 canvases, 3 new images in the image store" in out
    assert "failed: Mob/0100100.img stand/broken:" in out
    assert out.splitlines()[-1] == (
        "1 canvas failed (a link naming nothing), recorded in the manifest"
    )
    assert len(list((root / "extractions").iterdir())) == 1


def test_extracting_again_says_the_build_is_the_latest_again(
    client: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["extract", "--client", str(client), "--root", str(tmp_path / "s")]
    main(arguments)
    capsys.readouterr()

    assert main(arguments) == 0

    assert "was already extracted: it is the latest again" in capsys.readouterr().out


def test_a_relative_root_extracts_and_runs_retention_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = write_client(tmp_path / "a" / "Data", 1)
    second = write_client(tmp_path / "b" / "Data", 2)
    monkeypatch.chdir(tmp_path)

    codes = [
        main(["extract", "--client", str(client), "--root", "store"])
        for client in (first, second)
    ]

    assert codes == [0, 0], capsys.readouterr().err
    store = tmp_path / "store"
    builds = [folder.name for folder in (store / "extractions").iterdir()]
    assert len(builds) == 2
    assert not any(build.startswith(".") for build in builds)
    referenced: set[str] = set()
    for build in builds:
        referenced |= referenced_images(store / "extractions" / build / "raw.sqlite")
    assert {file.stem for file in (store / "images").rglob("*.png")} == referenced


def test_status_reports_missing_then_fresh_then_stale(
    client: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "store"
    arguments = ["--client", str(client), "--root", str(root)]

    main(["status", *arguments])
    assert capsys.readouterr().out.startswith("missing:")
    main(["extract", *arguments])
    capsys.readouterr()
    main(["status", *arguments])
    assert capsys.readouterr().out.startswith("fresh:")
    (client / "Sound" / "Sound.wz").write_bytes(b"not the same archive")
    main(["status", *arguments])
    assert capsys.readouterr().out.startswith("stale:")


def test_an_unreadable_client_is_an_error_not_an_extraction(
    client: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (client / "Sound" / "Sound.wz").write_bytes(b"not an archive")
    root = tmp_path / "store"

    code = main(["extract", "--client", str(client), "--root", str(root)])

    assert code == 1
    assert capsys.readouterr().err.startswith("error: archive ")
    assert not any((root / "extractions").iterdir())


def test_a_client_path_that_isnt_a_folder_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["status", "--client", str(tmp_path / "nowhere")])

    assert code == 1
    assert "doesn't exist" in capsys.readouterr().err


# --- the catalogue: extract builds it, show and search read it --------------


@pytest.fixture
def maps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    The catalogue fixture's client extracted through the command, into a
    store; the store. Then the client path can't be found, so `show` and
    `search` can't be leaning on it.
    """
    client = write_map_client(tmp_path / "Data")
    root = tmp_path / "store"
    assert main(["extract", "--client", str(client), "--root", str(root)]) == 0

    def no_client(explicit: Path | None = None) -> Path:
        raise ClientPathNotSet("no client path is set")

    monkeypatch.setattr("game_data.cli.client_data_path", no_client)
    return root


def test_extract_builds_the_catalogue_and_says_so(
    client: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "store"

    main(["extract", "--client", str(client), "--root", str(root)])

    assert (
        f"catalogue built, schema version {SCHEMA_VERSION}" in capsys.readouterr().out
    )
    (folder,) = (root / "extractions").iterdir()
    assert Manifest.read(folder).catalogue_schema_version == SCHEMA_VERSION
    assert (folder / "catalogue.sqlite").is_file()


def test_show_map_prints_a_map_found_by_name_as_json(
    maps: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["show", "map", "Victoria Road: Henesys", "--root", str(maps)])

    shown = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (shown["id"], shown["name"], shown["street"]) == (
        100,
        "Henesys",
        "Victoria Road",
    )
    assert shown["vr"] == {"left": -100, "top": -200, "right": 900, "bottom": 300}
    assert [s["name"] for s in shown["spawns"]] == ["Snail", "Regular Cab"]
    assert len(shown["footholds"]) == 7


def test_show_map_takes_an_id(maps: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "map", "300", "--root", str(maps)]) == 0

    assert json.loads(capsys.readouterr().out)["vr_derived"] is True


def test_show_map_with_a_name_that_matches_several_lists_them(
    maps: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["show", "map", "Mushroom Town", "--root", str(maps)])

    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("error: 'Mushroom Town' names 2 maps: ")
    assert "(200)" in err
    assert "(201)" in err


def test_show_map_with_an_unknown_name_lists_the_closest(
    maps: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["show", "map", "Henesis", "--root", str(maps)]) == 1

    assert "the closest are: Henesys" in capsys.readouterr().err


def test_search_prints_what_matches_with_ids_as_json(
    maps: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["search", "mushroom", "--kind", "map", "--root", str(maps)])

    assert code == 0
    assert json.loads(capsys.readouterr().out) == [
        {"kind": "map", "id": 200, "name": "Maple Road: Mushroom Town"},
        {"kind": "map", "id": 201, "name": "Rainbow Street: Mushroom Town"},
    ]


def test_show_with_no_extraction_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["show", "map", "Henesys", "--root", str(tmp_path / "empty")])

    assert code == 1
    assert "has no extraction" in capsys.readouterr().err
