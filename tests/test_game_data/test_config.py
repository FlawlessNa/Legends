"""
`game_data.config`: where the client path comes from, against temporary configs.
"""

import configparser
from pathlib import Path

import pytest

from game_data import config
from game_data.config import ClientPathNotSet, client_data_path


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
