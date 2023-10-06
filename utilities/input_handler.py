import asyncio
import ctypes
import win32api
import win32con

from ctypes import wintypes
from functools import cached_property

# http://www.kbdedit.com/manual/low_level_vk_list.html
# https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes

EXTENDED_KEYS = ['alt_right',
                 'ctrl_right',
                 'insert',
                 'home',
                 'pageup',
                 'delete',
                 'end',
                 'pagedown',
                 'left',
                 'right',
                 'up',
                 'down',
                 'num_lock',
                 'break',
                 'print_screen',
                 'divide',
                 'enter']
KEYBOARD_MAPPING = {

}
SYS_KEYS = ['alt', 'alt_right', 'F10']
MAPVK_VK_TO_VSC = 0
MAPVK_VSC_TO_VK = 1
MAPVK_VK_TO_CHAR = 2
MAPVK_VSC_TO_VK_EX = 3
MAPVK_VK_TO_VSC_EX = 4


class InputHandler:
    def __init__(self, handle: int, ign: str) -> None:
        """
        :param handle: Handle to the window that will be controlled
        :param ign: Associated IGN of the character from that window. Used to retrieve proper keybindings.
        """
        self.handle = handle
        self.ign = ign

    async def _post_message(self, key: str, *args, **kwargs) -> None:

        down_command = win32con.WM_SYSKEYDOWN if key in SYS_KEYS else win32con.WM_KEYDOWN
        up_command = win32con.WM_SYSKEYUP if key in SYS_KEYS else win32con.WM_KEYUP

        # Will return false if the message was not successfully posted, which may happen when the message Queue is full? # TODO - test if this necessary, probably not.
        while not win32api.PostMessage(*args, **kwargs):
            await asyncio.sleep(0.01)

    async def _send_input(self, *args, **kwargs) -> None:
        pass

    def _low_param_constructor(self,
                               key: int,
                               command: int,
                               extended_key: bool,
                               scan_code: int | None = None,
                               repeat_count: int = 1,
                               previous_key_state: int | None = None,
                               context_code: int | None = None
                               ) -> wintypes.LPARAM:
        """
        Creates the LPARAM argument for the PostMessage function.
        :param key: Key that will be sent through PostMessage
        :param command: Type of message to be sent. Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP.
        :param extended_key: Whether the key being press is part of the extended keys.
        :param scan_code:
        :param repeat_count: Number of times the key will be pressed. Default is 1. NOTE - Anything else won't work for now. This may be due to how the game handles these messages.  #TODO - Try inputting a large number and see what happens
        :param previous_key_state: 1 to simulate that the key is down while the key is pressed. 0 otherwise.
        :param context_code: 1 to simulate that the ALT key is down while the key is pressed OR if the key to press is the ALT key. 0 otherwise.
        :return:
        """
        assert command in [win32con.WM_KEYDOWN, win32con.WM_KEYUP, win32con.WM_SYSKEYDOWN, win32con.WM_SYSKEYUP], f"Command {command} is not supported"
        assert repeat_count < 2 ** 16

        if scan_code is None:
            ctypes.windll.user32.MapVirtualKeyExW.restype = wintypes.UINT
            ctypes.windll.user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HKL]
            scan_code = ctypes.windll.user32.MapVirtualKeyExW(key, MAPVK_VK_TO_VSC_EX, self._keyboard_layout_handle)

        # Handle the context code and correct command code if necessary
        if context_code is None:
            context_code = 1 if command in [win32con.WM_SYSKEYDOWN, win32con.WM_SYSKEYUP] and key == win32con.VK_MENU else 0

        # Use SYS KEYDOWN/SYS KEYUP if the key is the ALT key or if a different key is being pressed while the ALT key is simulated to be down.
        if context_code is 1 or key == win32con.VK_MENU or key == win32con.VK_F10:
            if command == win32con.WM_KEYDOWN:
                command = win32con.WM_SYSKEYDOWN
            elif command == win32con.WM_KEYUP:
                command = win32con.WM_SYSKEYUP

        # Handle the previous key state flag
        if previous_key_state is None:
            previous_key_state = 1 if command in [win32con.WM_KEYUP, win32con.WM_SYSKEYUP] else 0

        # Handle the transition flag. Always 0 for key down, 1 for key up.
        transition_state = 0 if command in [win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN] else 1

        return wintypes.LPARAM(repeat_count
                               | (scan_code << 16)
                               | (extended_key << 24)
                               | (context_code << 29)
                               | (previous_key_state << 30)
                               | (transition_state << 31)
                               )

    @cached_property
    def _keyboard_layout_handle(self) -> wintypes.HKL:
        """
        :return: Handle to the keyboard layout of the window.
        """
        ctypes.windll.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, wintypes.LPDWORD]

        ctypes.windll.user32.GetKeyboardLayout.restype = wintypes.HKL
        ctypes.windll.user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]

        thread_id = ctypes.windll.user32.GetWindowThreadProcessId(self.handle)
        return ctypes.windll.user32.GetKeyboardLayout(thread_id)
