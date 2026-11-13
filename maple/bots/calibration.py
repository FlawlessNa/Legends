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
          map: "Victoria Road: Ellinia"
          character_class: Swordsman
          trial_schedule: physics

    There is no `models_path`: this bot detects no mobs and no character (its
    position comes from the minimap and the screen), so it loads no model. A bot
    that does hit mobs still needs one.

    `character_class` is needed because it picks the skill table the bot's
    readers and Movement Plans work from: which buffs are looked for on screen,
    and whether the character can Teleport (a Plan casts it only when the class
    has it, and the `teleport` batch needs a class that does). Name the
    character's own class: `Swordsman` has no skills, so its Plans walk, jump
    and climb only. A class that is not in `maple/model/characters` refuses the
    start and lists the ones that are.

    The schedule's `map` must be the bot's: `TrialRunner` refuses to start on
    another map. The Session ends by itself once the schedule has finished.
    """

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [TrialRunner]
