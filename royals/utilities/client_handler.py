import win32gui

from .config_reader import config_reader


def get_open_clients(window_titles: list[str] = eval(config_reader('game', 'Client', 'Window Titles')),
                     window_class: str = config_reader('game', 'Client', 'Class Name')) -> list[int]:
    """
    Get all the windows that are titled with the provided titles.
    By default, the titles are read from the config file.
    :param window_titles: List of strings representing the window titles to look for.
    :param window_class: String representing the window class name.
    :return: List of Window objects.
    """
    def _enum_window_callback(hwnd, window_list):
        if win32gui.GetWindowText(hwnd) in window_titles:
            window_list.append(hwnd)
    result = []
    win32gui.EnumWindows(_enum_window_callback, result)
    return result
