import multiprocessing

from functools import partial

from botting.core import DecisionEngine, Executor, DecisionGenerator
from botting.models_abstractions import BaseMap, BaseCharacter

from royals import royals_ign_finder, RoyalsData
from royals.bot_implementations.generators import hit_mobs, rebuff, smart_rotation


class TrainingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(self,
                 log_queue: multiprocessing.Queue,
                 bot: Executor,
                 game_map: BaseMap,
                 character: BaseCharacter,
                 training_skill: str,
                 ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.update(
            "current_minimap_area_box",
            "current_minimap_position",
            "current_entire_minimap_box",
            current_minimap=game_map.minimap,
            current_mobs=game_map.mobs,
            character=character,
        )

        self._training_skill = self.game_data.character.skills[training_skill]
        self._teleport_skill = self.game_data.character.skills.get('Teleport')

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        return [
            rebuff.Rebuff(self.game_data, self.game_data.character.skills['Holy Symbol'])
        ]

    def next_map_rotation(self) -> list[callable]:
        return [
            partial(smart_rotation, self.game_data, self.rotation_lock, teleport=self._teleport_skill),
            partial(hit_mobs, self.game_data, self._training_skill)
        ]

    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return []
