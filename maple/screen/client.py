"""Finding the one MapleStory client this machine runs."""

from botting.screen import find_window
from botting.utilities import config_reader


def find_client() -> int:
    """
    The client's window handle, found by `configs/game.ini` `[Client]`
    `Class Name` and `Executable`. Neither the window title nor the screen is read.

    :raises WindowNotFound: when the client isn't running.
    :raises MultipleWindows: when more than one window matches.
    """
    class_name = str(config_reader("game", "Client", "Class Name"))
    executable = str(config_reader("game", "Client", "Executable"))
    return find_window(class_name, executable)
