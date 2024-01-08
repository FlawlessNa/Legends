"""
Exports the necessary functions from windll.user32 to be used by the input module.
Retrieves appropriate virtual key code given keyboard layout and key name.
"""
import ctypes
import win32api
import win32con

from ctypes import wintypes
from functools import lru_cache

# http://www.kbdedit.com/manual/low_level_vk_list.html
# https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes


KEYBOARD_MAPPING = {
    "alt": win32con.VK_MENU,
    "alt_right": win32con.VK_MENU,  # Could've used the win32con.VK_RMENU, but Spy++ shows that the game uses the VK_MENU instead. Reproduced here to copy human-like behavior.
    "ctrl": win32con.VK_CONTROL,  # Could've used the win32con.VK_LCONTROL, but Spy++ shows that the game uses the VK_CONTROL instead. Reproduced here to copy human-like behavior.
    "ctrl_right": win32con.VK_CONTROL,  # Could've used the win32con.VK_RCONTROL, but Spy++ shows that the game uses the VK_CONTROL instead. Reproduced here to copy human-like behavior.
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "shift": win32con.VK_SHIFT,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "insert": win32con.VK_INSERT,
    "delete": win32con.VK_DELETE,
    "pageup": win32con.VK_PRIOR,
    "pagedown": win32con.VK_NEXT,
    "num_lock": win32con.VK_NUMLOCK,
    "space": win32con.VK_SPACE,
    'enter': win32con.VK_RETURN,
}

EXTENDED_KEYS = (
    "alt_right",
    "ctrl_right",
    "insert",
    "home",
    "pageup",
    "delete",
    "end",
    "pagedown",
    "left",
    "right",
    "up",
    "down",
    "num_lock",
    "break",
    "print_screen",
    "divide",
    "enter",
    "num_lock",
)

MAPVK_VK_TO_VSC = 0
MAPVK_VSC_TO_VK = 1
MAPVK_VK_TO_CHAR = 2
MAPVK_VSC_TO_VK_EX = 3
MAPVK_VK_TO_VSC_EX = 4


def _setup_exported_functions() -> dict[str, callable]:
    """
    :return: Dictionary of exported functions from the ctypes.windll module.
    """
    map_virtual_key = ctypes.windll.user32.MapVirtualKeyExW
    map_virtual_key.restype = wintypes.UINT
    map_virtual_key.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HKL]

    get_window_thread_process_id = ctypes.windll.user32.GetWindowThreadProcessId
    get_window_thread_process_id.restype = wintypes.DWORD
    get_window_thread_process_id.argtypes = [wintypes.HWND, wintypes.LPDWORD]

    get_keyboard_layout = ctypes.windll.user32.GetKeyboardLayout
    get_keyboard_layout.restype = wintypes.HKL
    get_keyboard_layout.argtypes = [wintypes.DWORD]

    post_message = ctypes.windll.user32.PostMessageW
    post_message.restype = wintypes.BOOL
    post_message.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]

    # Note - The argtypes of SendInput is defined in each function type,
    # since the array length may change at each call.
    send_input = ctypes.windll.user32.SendInput
    send_input.restype = wintypes.UINT

    return {
        "MapVirtualKeyExW": map_virtual_key,
        "GetWindowThreadProcessId": get_window_thread_process_id,
        "GetKeyboardLayout": get_keyboard_layout,
        "PostMessageW": post_message,
        "SendInput": send_input,
    }


_EXPORTED_FUNCTIONS = _setup_exported_functions()


def _get_virtual_key(key: str, case_sensitive: bool, layout: wintypes.HKL) -> int:
    """
    :param key: String representation of the key to be pressed.
    :param layout: Handle to the keyboard layout of the window.
    :return: Virtual key code associated with the key.
    """
    if len(key) == 1 and case_sensitive:
        return ord(key)
    elif len(key) == 1:
        return win32api.LOBYTE(win32api.VkKeyScanEx(key, layout))
    else:
        return KEYBOARD_MAPPING[key]


@lru_cache
def _keyboard_layout_handle(hwnd: int) -> wintypes.HKL:
    """
    :param hwnd: Handle to the window to send the message to.
    :return: Handle to the keyboard layout of the window.
    """
    thread_id = _EXPORTED_FUNCTIONS["GetWindowThreadProcessId"](
        wintypes.HWND(hwnd), None
    )
    return _EXPORTED_FUNCTIONS["GetKeyboardLayout"](thread_id)
