import logging

from botting import PARENT_LOG
from botting.core import DecisionMaker
from maple.decision_makers import TrialRunner

from .maple_bot import MapleBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class CalibrationBot(MapleBot):
    """
    A real Session with exactly one DecisionMaker: the instrument movement
    calibration is measured with.

    One and only one, deliberately. A Trial measures how the movement loop
    converges, and every other DecisionMaker moves the character, casts, or opens a
    menu - each of which perturbs the thing being measured while leaving the record
    looking clean.

    Launched like any other bot, through a profile::

        ign: YourChar
        bot: calibration
        settings:
          game_map: GhostShip1
          trial_schedule: example
    """

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [TrialRunner]
