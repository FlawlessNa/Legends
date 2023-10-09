import asyncio
import functools
from typing import Literal

import pydirectinput
import time

from core import SharedResources
from utilities import config_reader, InputHandler, randomize_params


class Controller(InputHandler):
    """
    Controller class for the game. Contains methods for interacting with the game.
    Must be initialized with a handle to the game client, along with the IGN of the associated character. The IGN is used to retrieve key bindings from the config file.
    Each process should have its own controller instance, as each process will have its own game client.
    """
    def __init__(self, handle: int, ign: str) -> None:
        """
        :param handle: Handle to the window that will be controlled
        :param ign: Associated IGN of the character from that window
        """
        super().__init__(handle)
        self.ign = ign

    @functools.cached_property
    def key_binds(self) -> dict[str, str]:
        """
        Retrieves the key bindings for the associated character from the keybind config file.
        The configs cannot be changed while the bot is running. In-game key binds should therefore not be changed either.
        """
        return dict(config_reader('keybindings', f'{self.ign} - Keys', verbose=True))

    @SharedResources.return_focus_to_owner
    @SharedResources.requires_focus
    @randomize_params('duration', 'delay', perc_threshold=0.1)
    async def hold_key(self, key: str, duration: float, spam_secondary_key: str | None = None, delay: float | None = None) -> None:
        """
        Requires focus. Holds down the key for the specified duration. If a secondary key is provided, it will be spammed while the key is held down. Can be used to enter portals while moving.
        :param key: String representation of the key to be held down.
        :param duration: Duration in seconds to hold down the key. This is randomized slightly to prevent detection.
        :param spam_secondary_key: String representation of the key to be spammed while the primary key is held down.
        :param delay: Passed on to controller.press() method. Only used when secondary key is specified.
        :return: None
        """
        if delay is not None:
            assert delay >= 0, f"Delay ({delay}) must be a positive number"

        self.activate()
        try:
            pydirectinput.keyDown(key)
            if spam_secondary_key is not None:
                now = time.time()
                while time.time() - now < duration:
                    await self.press(spam_secondary_key, silenced=True, cooldowm=delay)
            else:
                await asyncio.sleep(duration)
        finally:
            pydirectinput.keyUp(key)

    async def press(self, key: str, silenced: bool = False, cooldown: float = 0.1, enforce_delay: bool = False, **kwargs) -> None:
        """
        # TODO - deal with keys/skills/macros variants
        :param key: String representation of the key to be pressed.
        :param silenced: Whether to activate the window before pressing the key. If True, the key is sent through PostMessage(...) instead of SendInput(...).
        :param cooldown: Delay between each call to this function. However, several keys/inputs may be sent at once, and cooldown is only applied at the very end.
            Note: To control delay between each keys/inputs on a single call, pass in 'delay' as a keyword argument. Each delay will be slightly randomized.
        :param enforce_delay: Only applicable when silenced = False. If several inputs are sent at once, this will enforce a delay between each input. Otherwise, they are all simultaneous.
        :return: None
        """
        if silenced:
            await self._non_focused_input(key, [win32con.WM_KEYDOWN, win32con.WM_KEYUP], cooldown=cooldown, **kwargs)
        else:
            await self._focused_input(key, ['keydown', 'keyup'], cooldown=cooldown, enforce_delay=enforce_delay, **kwargs)

    async def write(self, message: str, silenced: bool = True, cooldown: float = 0.1, enforce_delay: bool = True, **kwargs) -> None:
        """
        Write a message in the specified window. When silenced=True, We use the WM_CHAR command to allow for differentiation of lower and upper case letters. This by-passes the KEYDOWN/KEYUP commands.
        Therefore, this creates "non-human" inputs sent to the window and as such, should only be used to actually write stuff in the chat and nothing else (anti-detection prevention).
        Additionally, when silenced=False, the SendInput function creates VK_PACKETS with are sent to the window to replicate any custom chars. This also creates "non-human" behavior.
        :param message: Actual message to be typed.
        :param silenced: Whether to write input to the active window or not. If True, the key is sent through PostMessage(...) instead of SendInput(...).
        :param cooldown: Delay between each call to this function.
        :param enforce_delay: Only used when silenced=False. If false, the entire message is written instantly (looks like a copy/paste). If True, a delay is enforced between each char.
        :return: None
        """
        if silenced:
            await self._non_focused_input(list(message), [win32con.WM_CHAR] * len(message), cooldown=cooldown, **kwargs)

        else:
            message = [char for char in list(message) for _ in range(2)]
            events: list[Literal] = ['keydown', 'keyup'] * (len(message) // 2)
            await self._focused_input(list(message), events, cooldown=cooldown, as_unicode=True, enforce_delay=enforce_delay, **kwargs)

    @SharedResources.requires_focus
    async def move_mouse(self) -> None:
        """Requires focus because otherwise the window may not properly register mouse movements. In such a case, if mouse blocks visuals, it will keep blocking them."""
        pass


if __name__ == '__main__':
    from asyncio import run
    import win32con
    handle = 0x001A05F2
    test = Controller(handle, 'FarmFest1')
    run(test.press('a', silenced=False, enforce_delay=False))
    run(test.press("a", silenced=False, enforce_delay=True))
    # run(test.press("pageup", silenced=True))
