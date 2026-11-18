"""
The game window's handle, which every Bot has: input goes to it.

`Bot.child_init` looks it up with `Bot.find_handle` and builds `WindowProvider`
with it, so `HANDLE` is the first Data Key a Bot serves. Unported code reads it
as `data.handle`, as it always has.
"""

from typing import Any

from .data_keys import Key, Provider


class WindowProvider(Provider):
    """
    Serves `HANDLE`: the handle `Bot.find_handle` found when the Bot started.

    Bot-level: the Bot builds it in `child_init`, which already looked the
    window up, so `setup()` does no I/O.
    """

    bot_level = True

    def __init__(self, *args: Any, handle: int, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        """
        :param handle: The game window's handle, as `Bot.find_handle` found it.
        """
        super().__init__(*args, **settings)
        self.handle = handle

    def setup(self) -> None:
        self.register(HANDLE, lambda: self.handle)


#: The game window's handle. Never refreshed: a window keeps its handle.
HANDLE: Key[int] = Key("handle", provider=WindowProvider)
