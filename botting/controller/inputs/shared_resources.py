import asyncio
import ctypes
import functools
import logging

from win32gui import GetForegroundWindow, SetForegroundWindow

logger = logging.getLogger(__name__)

MOUSE = 0
KEYBOARD = 1
HARDWARE = 2


class SharedResources:
    """
    Helper class shared across all spawned processes.
    Manages a Lock to prevent multiple processes from trying to use PC Focus
    simultaneously.
    Additionally, it maintains a set of all keys that have been sent through SendInput
    during the lifecycle of the program. This set is used to inspect keys that may
    require releasing before a switch of window focus is performed.
    """

    focus_lock = asyncio.Lock()  # All instances of this class will share the same lock.
    # Used to prevent multiple processes from trying to use PC Focus simultaneously.

    keys_sent = set()

    @classmethod
    def requires_focus(cls, func: callable) -> callable:
        """
        Use this decorator to ensure a lock is acquired for any coroutine that
        require the PC focus (foreground window).
        :return: The function after the acquiring the lock.
        """

        @functools.wraps(func)
        async def inner(*args, **kwargs):
            """
            Lock is required to prevent multiple tasks or processes from trying
             to use PC Focus simultaneously.
            """
            await cls.focus_lock.acquire()
            try:
                res = await func(*args, **kwargs)
            finally:
                cls.focus_lock.release()
            return res

        return inner

    @staticmethod
    def return_focus_to_owner(func: callable) -> callable:
        """
        Ensures that the focus is returned to the original window after the function
        or coroutine is executed.
        """

        @functools.wraps(func)
        async def inner(*args, **kwargs):
            current_handle = GetForegroundWindow()
            ctypes.windll.user32.BlockInput(True)
            try:
                res = await func(*args, **kwargs)
            finally:
                ctypes.windll.user32.BlockInput(False)
            SetForegroundWindow(current_handle)
            return res

        return inner
