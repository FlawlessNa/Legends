"""Low-level module that handles the sending of inputs to any window through PostMessage(...)."""
import asyncio
import ctypes
import win32con

from ctypes import wintypes

from utilities.inputs import _InputsHelpers
from utilities.randomize_params import randomize_params

from functools import lru_cache

SYS_KEYS = ["alt", "alt_right", "F10"]


class _NonFocusedInputs(_InputsHelpers):
    """Low-level class that handles the sending of inputs to any window through PostMessage(...). Consecutive messages may be sent with a delay between each call."""

    async def _post_messages(
        self, items: list[list[tuple, float]], cooldown: float = 0.1
    ) -> None:
        """
        Sends the provided items through PostMessage(...) and waits the required delay between each call.
        Note: Delays are the waiting time between each call of PostMessage(...). These are usually very short, especially between and KEYDOWN and KEYUP messages.
            Cooldown, on the other end, is only waited after all messages were sent.
        :param items: full messages and delays to be sent. Returned by the _post_message_constructor method.
        :param cooldown: Cooldown after all messages have been sent. Default is 0.1 seconds.
        :return: None
        """
        for item in items:
            msg, delay = item

            # PostMessageW will return 0 only if the message queue is full. In that case, we wait until it's not full anymore. This shouldn't really ever happen but still a precaution.
            while not self._exported_functions["PostMessageW"](*msg):
                print("PostMessage has failed")
                await asyncio.sleep(
                    0.01
                )  # This will only be called if the message is not posted successfully.
            await asyncio.sleep(
                delay
            )  # Allows for smaller delays between consecutive keys, such as when writing a message in-game, or between KEYUP/KEYDOWN commands.
        await asyncio.sleep(cooldown)

    def _message_constructor(
        self,
        keys: list[str],
        messages: list[wintypes.UINT],
        delay: float = 0.033,  # This is somewhat similar to the automatic repeat feature for my keyboard. It's not perfect, but it's close enough.
        hwnd: int | None = None,
        **kwargs,
    ) -> list[
        list[
            tuple[wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], float
        ]
    ]:
        """
        Constructs the appropriate array of input that will be sent to the window associated with the provided handle through PostMessage(...).
        :param keys: List of string representation of the key(s) to be pressed.
        :param messages: Type of message to be sent. Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_CHAR. If it is a list, it must be the same length as the keys list.
        :param delay: Cooldown between each call of PostMessage(...). Default is 0.03 seconds.
        :param hwnd: Handle to the window to send the message to. If None, the handle associated with this instance will be used.
        :param kwargs: Additional arguments to be passed to the _low_param_constructor method.
        :return: list of list[tuples, float]. Each tuple contains all necessary argument to be passed to PostMessage through simple unpacking. Each float is the delay between each call of PostMessage.
        """
        return_val = list()
        assert isinstance(keys, list) and isinstance(
            messages, list
        ), f"Keys and messages must be lists."
        assert len(keys) == len(
            messages
        ), f"Msg and keys must have the same length when they are provided as lists."
        for key, msg in zip(keys, messages):
            return_val.append(
                self._single_message_constructor(
                    key, msg, delay=delay, hwnd=hwnd, **kwargs
                )
            )
        return return_val

    @randomize_params("delay")
    def _single_message_constructor(
        self,
        key: str,
        message: wintypes.UINT,
        delay: float,
        hwnd: int | None = None,
        **kwargs,
    ) -> list[
        tuple[wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], float
    ]:
        """
        Constructs the appropriate inputs that will be sent to the window associated with the provided handle through PostMessage(...). Additionally, delay is passed to this method to allow for
        a different randomized value between each message.
        :param key: String representation of the key to be pressed.
        :param message: Type of message to be sent. Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_CHAR.
        :param delay: Cooldown between each call of PostMessage(...). Will be randomized.
        :param hwnd: Handle to the window to send the message to. If None, the handle associated with this instance will be used.
        :param kwargs: Additional arguments to be passed to the _low_param_constructor method.
        :return: list[tuples, float]. The tuple contains all necessary argument to be passed to PostMessage through simple unpacking. The float is the delay between each call of PostMessage.
        """
        if hwnd is None:
            hwnd = self.handle

        if key in SYS_KEYS:
            message = (
                win32con.WM_SYSKEYDOWN if message == win32con.WM_KEYDOWN else message
            )
            message = win32con.WM_SYSKEYUP if message == win32con.WM_KEYUP else message

        extended_key = int(key in self.EXTENDED_KEYS)
        vk_key = self._get_virtual_key(
            key,
            True if message == win32con.WM_CHAR else False,
            self._keyboard_layout_handle(hwnd),
        )
        l_params = self._low_param_constructor(
            key=vk_key, command=message, extended_key=extended_key, hwnd=hwnd, **kwargs
        )
        return [
            (
                wintypes.HWND(hwnd),
                wintypes.UINT(message),
                wintypes.WPARAM(vk_key),
                l_params,
            ),
            delay,
        ]

    def _low_param_constructor(
        self,
        key: int,
        command: int,
        extended_key: int,
        scan_code: int | None = None,
        repeat_count: int = 1,
        previous_key_state: int | None = None,
        context_code: int | None = None,
        hwnd: int | None = None,
    ) -> wintypes.LPARAM:
        """
        Creates the LPARAM argument for the PostMessage function.
        :param key: Key that will be sent through PostMessage
        :param command: Type of message to be sent. Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP.
        :param extended_key: Whether the key being press is part of the extended keys.
        :param scan_code: The scan code associated with the key. If None, it will be determined automatically.
        :param repeat_count: Number of times the key will be pressed. Default is 1. NOTE - Anything else won't work for now. This may be due to how the game handles these messages.
        :param previous_key_state: 1 to simulate that the key is down while the key is pressed. 0 otherwise.
        :param context_code: 1 to simulate that the ALT key is down while the key is pressed OR if the key to press is the ALT key. 0 otherwise.
        :param hwnd: Handle to the window to send the message to. If None, the handle associated with this InputHandler instance will be used. Used here to determine keyboard layout.
        :return: LPARAM argument for the PostMessage function.
        """
        assert command in [
            win32con.WM_KEYDOWN,
            win32con.WM_KEYUP,
            win32con.WM_SYSKEYDOWN,
            win32con.WM_SYSKEYUP,
            win32con.WM_CHAR,
        ], f"Command {command} is not supported"
        assert repeat_count < 2**16

        if scan_code is None:
            scan_code = self._exported_functions["MapVirtualKeyExW"](
                key, self.MAPVK_VK_TO_VSC_EX, self._keyboard_layout_handle(hwnd)
            )

        # Handle the context code and correct command code if necessary
        if context_code is None:
            # Note: Per online documentation, it should be if command in [win32con.WM_SYSKEYDOWN, win32con.WM_SYSKEYUP], but this is inconsistent with what Spy++ observes.
            context_code = (
                1
                if command == win32con.WM_SYSKEYDOWN and key == win32con.VK_MENU
                else 0
            )

        # Use SYS KEYDOWN/SYS KEYUP if the key is the ALT key or if a different key is being pressed while the ALT key is simulated to be down.
        if context_code == 1 or key == win32con.VK_MENU or key == win32con.VK_F10:
            if command == win32con.WM_KEYDOWN:
                command = win32con.WM_SYSKEYDOWN
            elif command == win32con.WM_KEYUP:
                command = win32con.WM_SYSKEYUP

        # Handle the previous key state flag
        if previous_key_state is None:
            previous_key_state = (
                1 if command in [win32con.WM_KEYUP, win32con.WM_SYSKEYUP] else 0
            )

        # Handle the transition flag. Always 0 for key down, 1 for key up.
        transition_state = (
            0 if command in [win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN] else 1
        )

        return wintypes.LPARAM(
            repeat_count
            | (scan_code << 16)
            | (extended_key << 24)
            | (context_code << 29)
            | (previous_key_state << 30)
            | (transition_state << 31)
        )

    def _setup_exported_functions(self) -> dict[str, callable]:
        """
        :return: Dictionary of exported functions from the ctypes.windll module Expands method from InputHelpers to add PostMessageW.
        """
        post_message = ctypes.windll.user32.PostMessageW
        post_message.restype = wintypes.BOOL
        post_message.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        return {
            **super()._setup_exported_functions(),
            "PostMessageW": post_message,
        }
