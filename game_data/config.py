"""
Where the installed client's `Data` folder is, which is set per machine.

The path comes from, in order:

1. an explicit argument, such as the CLI's `--client`;
2. `[Client] Data` in `configs/game_data.ini`, which is gitignored. Copy
   `configs/game_data.example.ini` to create it.

With neither, `client_data_path` raises `ClientPathNotSet`, naming the file to
create. There is no default, so a machine with the client somewhere else can't
quietly read the wrong folder.

`STORE` is where extractions go by default: `data/game_data`, which is
gitignored. Every entry point takes the store root, so tests use their own.
"""

import configparser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "configs" / "game_data.ini"
EXAMPLE = REPO / "configs" / "game_data.example.ini"
STORE = REPO / "data" / "game_data"

_SECTION = "Client"
_KEY = "Data"


class ClientPathNotSet(Exception):
    """No client path was given, and the config file doesn't set one."""


def client_data_path(explicit: Path | None = None, *, config: Path = CONFIG) -> Path:
    """
    The client's `Data` folder.

    :param explicit: Wins when given.
    :param config: The config file to read otherwise.
    :raises ClientPathNotSet: Neither gives a path.
    :raises NotADirectoryError: The path given isn't a folder.
    """
    if explicit is not None:
        return _existing(explicit, "the path given")
    if not config.is_file():
        raise ClientPathNotSet(
            f"no client path is set: create {config} by copying "
            f"{config.with_name(EXAMPLE.name)}, and set [{_SECTION}] {_KEY} "
            "to the client's MSCW\\Data folder"
        )
    parser = configparser.ConfigParser()
    parser.read(config, encoding="utf-8")
    value = parser.get(_SECTION, _KEY, fallback="").strip()
    if not value:
        raise ClientPathNotSet(
            f"{config} doesn't set [{_SECTION}] {_KEY}: copy it from "
            f"{config.with_name(EXAMPLE.name)}, and set it to the client's "
            "MSCW\\Data folder"
        )
    return _existing(Path(value), str(config))


def _existing(path: Path, source: str) -> Path:
    if not path.is_dir():
        raise NotADirectoryError(
            f"the client data folder {path}, from {source}, doesn't exist"
        )
    return path
