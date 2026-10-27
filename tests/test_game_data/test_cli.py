"""
`python -m game_data extract` and `status`, through `cli.main`, against the
synthetic client of `test_extraction`.
"""

from pathlib import Path

import pytest

from game_data.cli import main
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
