"""
`game_data.config`: where the client path, the store and the frames come from,
against temporary configs.
"""

import configparser
from collections.abc import Callable
from pathlib import Path

import pytest

from game_data import config
from game_data.config import (
    ClientPathNotSet,
    client_data_path,
    frames_root,
    store_root,
)


@pytest.fixture
def client(tmp_path: Path) -> Path:
    folder = tmp_path / "MSCW" / "Data"
    folder.mkdir(parents=True)
    return folder


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "game_data.ini"
    path.write_text(text, encoding="utf-8")
    return path


def test_an_explicit_path_wins_over_the_config(tmp_path: Path, client: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    ini = _config(tmp_path, f"[Client]\nData = {elsewhere}\n")

    assert client_data_path(client, config=ini) == client


def test_the_config_gives_the_path_without_an_explicit_one(
    tmp_path: Path, client: Path
) -> None:
    ini = _config(tmp_path, f"[Client]\nData = {client}\n")

    assert client_data_path(config=ini) == client


def test_with_neither_the_error_names_the_file_to_create_and_the_example(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "game_data.ini"

    with pytest.raises(ClientPathNotSet) as caught:
        client_data_path(config=missing)

    assert str(missing) in str(caught.value)
    assert "game_data.example.ini" in str(caught.value)


@pytest.mark.parametrize("text", ["", "[Client]\n", "[Client]\nData =\n", "[x]\n"])
def test_a_config_that_sets_no_path_raises(tmp_path: Path, text: str) -> None:
    ini = _config(tmp_path, text)

    with pytest.raises(ClientPathNotSet, match="game_data.example.ini"):
        client_data_path(config=ini)


def test_a_path_that_is_not_a_folder_raises_naming_where_it_came_from(
    tmp_path: Path,
) -> None:
    ini = _config(tmp_path, f"[Client]\nData = {tmp_path / 'nowhere'}\n")

    with pytest.raises(NotADirectoryError, match="game_data.ini"):
        client_data_path(config=ini)
    with pytest.raises(NotADirectoryError, match="the path given"):
        client_data_path(tmp_path / "nowhere", config=ini)


def test_the_default_config_is_the_gitignored_one_beside_its_example() -> None:
    assert config.CONFIG.parent == config.EXAMPLE.parent
    assert config.CONFIG.name == "game_data.ini"
    assert config.EXAMPLE.is_file()
    ignored = (config.REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "configs/game_data.ini" in ignored


def test_the_example_sets_the_steam_default() -> None:
    parser = configparser.ConfigParser()
    parser.read(config.EXAMPLE, encoding="utf-8")

    assert parser.get("Client", "Data").endswith(r"MapleStory\MSCW\Data")


# --- the store and frames roots ----------------------------------------------

ROOTS = [
    pytest.param(store_root, "Store", config.DEFAULT_STORE, id="store"),
    pytest.param(frames_root, "Frames", config.DEFAULT_FRAMES, id="frames"),
]

type Resolve = Callable[..., Path]


@pytest.mark.parametrize(("resolve", "section", "default"), ROOTS)
def test_an_explicit_root_wins_over_the_config(
    tmp_path: Path, resolve: Resolve, section: str, default: Path
) -> None:
    ini = _config(tmp_path, f"[{section}]\nRoot = {tmp_path / 'configured'}\n")

    assert resolve(tmp_path / "given", config=ini) == tmp_path / "given"
    assert resolve(tmp_path / "given", config=ini) != default


@pytest.mark.parametrize(("resolve", "section", "default"), ROOTS)
def test_the_config_gives_the_root_without_an_explicit_one(
    tmp_path: Path, resolve: Resolve, section: str, default: Path
) -> None:
    ini = _config(tmp_path, f"[{section}]\nRoot = {tmp_path / 'configured'}\n")

    assert resolve(config=ini) == tmp_path / "configured"
    assert resolve(config=ini) != default


@pytest.mark.parametrize(("resolve", "section", "default"), ROOTS)
def test_a_relative_root_in_the_config_is_taken_from_the_repo(
    tmp_path: Path, resolve: Resolve, section: str, default: Path
) -> None:
    ini = _config(tmp_path, f"[{section}]\nRoot = shared/here\n")

    assert resolve(config=ini) == config.REPO / "shared" / "here"
    assert resolve(config=ini) != default


@pytest.mark.parametrize(("resolve", "section", "default"), ROOTS)
@pytest.mark.parametrize(
    "text",
    [None, "", "[Client]\nData = x\n", "[{section}]\n", "[{section}]\nRoot =\n"],
)
def test_with_neither_the_root_is_the_default_under_data(
    tmp_path: Path, resolve: Resolve, section: str, default: Path, text: str | None
) -> None:
    if text is None:
        ini = tmp_path / "game_data.ini"
    else:
        ini = _config(tmp_path, text.format(section=section))

    assert resolve(config=ini) == default
    assert default.parent == config.REPO / "data"


def test_the_store_root_does_not_need_the_client_path(tmp_path: Path) -> None:
    """A config that sets only the store still resolves it; the client is separate."""
    ini = _config(tmp_path, f"[Store]\nRoot = {tmp_path}\n")

    assert store_root(config=ini) == tmp_path
    with pytest.raises(ClientPathNotSet):
        client_data_path(config=ini)


def test_the_example_documents_the_store_and_frames_roots() -> None:
    text = config.EXAMPLE.read_text(encoding="utf-8")

    assert "; [Store]\n; Root = " in text
    assert "; [Frames]\n; Root = " in text
