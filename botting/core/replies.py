"""
The replies switch: whether a Bot's automatic chat replies are on.

Every Bot has one, as it has a window handle: the engine's Discord grammar
switches it (`REPLIES OFF|ON`, and the takeover a `WRITE` implies), and
`Bot.replies` is what the command reaches. `Bot.child_init` builds
`RepliesProvider`, on, and `Bot.replies` switches it; a DecisionMaker that
replies declares `REPLIES_ON` in `reads` and reads it before each reply.
"""

from typing import Any

from .data_keys import Key, Provider


class RepliesProvider(Provider):
    """
    Serves `REPLIES_ON`: on when the Bot starts, then whatever `switch` last
    set it to.

    Bot-level: the Bot builds it in `child_init` and switches it from
    `Bot.replies`, so it does no I/O.
    """

    bot_level = True

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        self.on = True

    def setup(self) -> None:
        # No threshold: the value changes only when `switch` refreshes it.
        self.register(REPLIES_ON, lambda: self.on)

    def switch(self, on: bool) -> None:
        """Turn the Bot's automatic replies on or off, for every reader at once."""
        self.on = on
        self.refresh(REPLIES_ON)


#: Whether the Bot's automatic chat replies are on. Switched by `Bot.replies`.
REPLIES_ON: Key[bool] = Key("replies_on", provider=RepliesProvider)
