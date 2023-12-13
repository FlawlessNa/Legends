import win32gui

from .config_reader import config_reader


def get_open_clients(
    window_titles: list[str] = eval(config_reader("game", "Client", "Window Titles")),
) -> list[int]:
    """
    Get all the windows that are titled with the provided titles.
    By default, the titles are read from the config file.
    :param window_titles: List of strings representing the window titles to look for.
    :return: List of Window objects.
    """

    def _enum_window_callback(hwnd, window_list):
        if win32gui.GetWindowText(hwnd) in window_titles:
            window_list.append(hwnd)

    result = []
    win32gui.EnumWindows(_enum_window_callback, result)
    return result


def get_client_handle(ign: str, ign_finder: callable) -> int:
    """
    Returns the handle of the client with the provided IGN.
    :param ign: String representing the IGN to look for.
    :param ign_finder: Callable that returns the IGN of the client given its handle.
    :return: Integer representing the handle of the client.
    """
    for handle in get_open_clients():
        if ign_finder(handle) == ign:
            return handle
    raise ValueError(f"Client with IGN {ign} not found.")
