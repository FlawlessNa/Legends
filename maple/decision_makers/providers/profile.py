"""
What the Bot's profile says of how the character moves: its speed and jump
stats, and the Calibration constants its Movement Plans are compiled with.
"""

from typing import Any

from botting.core import Key, Provider
from maple.model.mechanics.physics import Calibration


class ProfileProvider(Provider):
    """
    Serves the profile's `speed_multiplier` and `jump_multiplier`, 1.00 when it
    sets none, and its `calibration` constants.

    Bot-level: `MapleBot` parses the constants when it is built, so a misspelt
    one refuses the start, and builds this Provider in `child_init`. `setup()`
    does no I/O. The ability menu's own reading of the stats is
    `AbilityMenuProvider`'s (`SPEED_MULTIPLIER`, `JUMP_MULTIPLIER`).
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        speed_multiplier: float = 1.00,
        jump_multiplier: float = 1.00,
        calibration: Calibration | None = None,
        **settings: object,
    ) -> None:
        """
        :param speed_multiplier: The profile's speed stat, as a multiplier.
        :param jump_multiplier: The profile's jump stat, as a multiplier.
        :param calibration: The profile's Calibration constants, parsed.
        """
        super().__init__(*args, **settings)
        self.speed_multiplier = speed_multiplier
        self.jump_multiplier = jump_multiplier
        self.calibration = calibration

    def setup(self) -> None:
        self.register(PROFILE_SPEED_MULTIPLIER, lambda: self.speed_multiplier)
        self.register(PROFILE_JUMP_MULTIPLIER, lambda: self.jump_multiplier)
        self.register(CALIBRATION, lambda: self.calibration)


#: The profile's speed stat, as a multiplier: what Movement Plans plan with
#: unless the ability menu was read (`SPEED_MULTIPLIER`).
PROFILE_SPEED_MULTIPLIER: Key[float] = Key("speed_multiplier", ProfileProvider)
#: The profile's jump stat, as a multiplier, as `PROFILE_SPEED_MULTIPLIER`.
PROFILE_JUMP_MULTIPLIER: Key[float] = Key("jump_multiplier", ProfileProvider)
#: The profile's Calibration constants, which Movement Plans' physics take.
CALIBRATION: Key[Calibration | None] = Key("calibration", ProfileProvider)
