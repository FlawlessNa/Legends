import asyncio
import os
import ctypes
import functools
import logging

from win32gui import GetForegroundWindow, SetForegroundWindow

logger = logging.getLogger(__name__)


class SharedResources:
    focus_lock = asyncio.Lock()  # All instances of this class will share the same lock.
    # Used to prevent multiple processes from trying to use PC Focus simultaneously.

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
                # logger.debug(f"Focus Lock {id(cls.focus_lock)} acquired by {os.getpid()}")
                res = await func(*args, **kwargs)
            finally:
                cls.focus_lock.release()
                # logger.debug(f"Focus Lock {id(cls.focus_lock)} released by {os.getpid()}")
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
