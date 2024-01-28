import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator
from royals import royals_ign_finder, RoyalsData
from royals.interface import AbilityMenu, CharacterStats
from .generators import DistributeAP, EnsureSafeSpot, PartyRebuff


class BuffMule(DecisionEngine):
    """
    Engine used for buff mules, which are usually leeching as well.
    """

    ign_finder = royals_ign_finder

    included_buffs = [
        "Haste",
        "Hyper Body",
        "Holy Symbol",
        "Sharp Eyes",
    ]

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        character: callable,
        notifier: multiprocessing.Event,
        barrier: multiprocessing.Barrier,
        rebuff_location: tuple[int, int] = None,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.update(
            ability_menu=AbilityMenu(),
            character=character(),
            character_stats=CharacterStats(),
        )
        self._buffs = []
        for buff in self.included_buffs:
            if self.game_data.character.skills.get(buff) is not None:
                self._buffs.append(self.game_data.character.skills[buff])
        print(self.ign, self._buffs)

        self._notifier = notifier
        self._barrier = barrier

        if rebuff_location:
            self._rebuff_location = rebuff_location
        else:
            self._rebuff_location = self.game_data.current_minimap.central_node

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[DecisionGenerator]:
        return [
            DistributeAP(self.game_data),
            EnsureSafeSpot(self.game_data),
            PartyRebuff(self.game_data,
                        self._notifier,
                        self._barrier,
                        self._buffs,
                        self._rebuff_location
                        ),
        ]

    def next_map_rotation(self) -> DecisionGenerator:
        pass

    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return []
