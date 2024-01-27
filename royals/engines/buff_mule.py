import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator
from royals import royals_ign_finder, RoyalsData
from royals.interface import AbilityMenu, CharacterStats
from .generators import DistributeAP, EnsureSafeSpot


class BuffMule(DecisionEngine):
    """
    Engine used for buff mules, which are usually leeching as well.
    """
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        character: callable,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.update(
            ability_menu=AbilityMenu(),
            character=character(),
            character_stats=CharacterStats(),
        )

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[DecisionGenerator]:
        return [
            DistributeAP(self.game_data),
            EnsureSafeSpot(self.game_data),
            PartyRebuff(self.game_data)  # TODO: Refactor for multiprocesses - use mp.Event to notify its time to rebuff, then use mp.Barrier to wait till all bots are ready
        ]

    def next_map_rotation(self) -> DecisionGenerator:
        pass

    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return []
