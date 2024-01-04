import multiprocessing

from functools import partial

from botting.core import DecisionEngine, Executor, DecisionGenerator
from botting.models_abstractions import BaseMap

from royals import royals_ign_finder, RoyalsData
from royals.generators import hit_mobs, SmartRotation, Rebuff


class TrainingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        game_map: BaseMap,
        character: callable,
        training_skill: str,
        buffs: list[str] | None = None,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.update(
            "current_minimap_area_box",
            "current_minimap_position",
            "current_entire_minimap_box",
            current_minimap=game_map.minimap,
            current_mobs=game_map.mobs,
            character=character(),
        )

        self._training_skill = self.game_data.character.skills[training_skill]
        self._teleport_skill = self.game_data.character.skills.get("Teleport")
        if buffs:
            self._buffs_to_use = [self.game_data.character.skills[buff] for buff in buffs]
        else:
            self._buffs_to_use = []
        for skill in self.game_data.character.skills.values():
            if (
                skill.type in ["Buff", "Party Buff"]
                and skill.use_by_default
                and skill not in self._buffs_to_use
            ):
                self._buffs_to_use.append(skill)

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        generators = []
        for skill in self.game_data.character.skills.values():
            if skill.type in ["Buff", "Party Buff"] and skill in self._buffs_to_use:
                generators.append(
                    Rebuff(self.game_data, skill)
                )
        return generators

    def next_map_rotation(self) -> list[callable]:
        return [
            SmartRotation(self.game_data, self.rotation_lock, teleport=self._teleport_skill),
            partial(hit_mobs, self.game_data, self._training_skill),
        ]

    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return []
