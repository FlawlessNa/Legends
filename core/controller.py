import asyncio
import functools
import pydirectinput
import time

from win32com.client import Dispatch
from win32gui import SetForegroundWindow

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
        The focus lock is used to prevent multiple processes from trying to use PC Focus simultaneously. This parameter is set manually by any process that needs it. Otherwise, it remains None.
        :param handle: Handle to the window that will be controlled
        :param ign: Associated IGN of the character from that window
        """
        super().__init__(handle, ign)

    def activate(self) -> None:
        """
        Activates the window associated with this controller. Any key press or mouse click will be sent to the active window.
        :return: None
        """
        shell = Dispatch("WScript.Shell")
        shell.SendKeys('%')
        SetForegroundWindow(self.handle)

    @functools.cached_property
    def key_binds(self) -> dict[str, str]:
        """
        Retrieves the key bindings for the associated character from the keybind config file.
        The configs cannot be changed while the bot is running. In-game key binds should therefore not be changed either.
        """
        return dict(config_reader('keybindings', f'{self.ign} - Keys', verbose=True))

    @SharedResources.return_focus_to_owner
    @SharedResources.lock_focus
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
                    await self.press(spam_secondary_key, silenced=True, delay=delay)
            else:
                await asyncio.sleep(duration)
        finally:
            pydirectinput.keyUp(key)

    async def press(self, key: str, silenced: bool = False, delay: float | None = None) -> None:
        """
        # TODO - deal with keys/skills/macros variants
        :param key: String representation of the key to be pressed.
        :param silenced: Whether to activate the window before pressing the key. If False, the key is sent through PostMessage(...) instead of pydirectinput.press(...).
        :param delay: # TODO - handle this properly
        :return:
        """
        if silenced:
            await self.post_message(key, self.handle, delay=delay)
        else:
            await self._non_silent_press(key, delay=delay)

    @SharedResources.lock_focus
    async def _non_silent_press(self, key: str, delay: float | None = None, **kwargs) -> None:
        """
        Requires focus. Presses the key.
        Called internally by controller.press() whenever silenced=False.
        :param key: String representation of the key to be pressed.
        :return:
        # TODO - deal with delays
        """
        self.activate()
        pydirectinput.press(key, **kwargs)


if __name__ == '__main__':
    from asyncio import run
    handle = 0x000206B0
    test = Controller(handle, 'FarmFest1')
    test.activate()
    pydirectinput.PAUSE = 1
    for _ in range(10):
        pydirectinput.press('right')

    # run(test._non_silent_press('up'))

