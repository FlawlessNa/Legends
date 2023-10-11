import asyncio
import ctypes
import functools

from win32gui import GetForegroundWindow, SetForegroundWindow


class SharedResources:
    focus_lock = (
        asyncio.Lock()
    )  # All instances of this class will share the same lock. This is used to prevent multiple processes from trying to use PC Focus simultaneously.

    @classmethod
    def requires_focus(cls, func: callable) -> callable:
        """
        Use this decorator to ensure a lock is acquired for any coroutine that require the PC focus (foreground window).
        In that sense, the lock is not required, but the decorator is still useful to ensure that the focus is returned to the original window after the function is executed.
        :return: The function after the acquiring the lock.
        """

        @functools.wraps(func)
        async def inner(*args, **kwargs):
            """Lock is required to prevent multiple tasks or processes from trying to use PC Focus simultaneously."""
            async with cls.focus_lock:  # Blocks until the lock is freed by the other process. Automatically frees the lock when the coroutine is finished.
                res = await func(*args, **kwargs)
            return res

        return inner

    @staticmethod
    def return_focus_to_owner(func: callable) -> callable:
        """Ensures that the focus is returned to the original window after the function or coroutine is executed."""

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
