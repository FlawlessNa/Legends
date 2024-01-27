import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator
from botting.models_abstractions import BaseMap

from royals import royals_ign_finder, RoyalsData

# from .generators import TelecastRotationGenerator, Rebuff, LocalizedRebuff, PetFood, MobCheck


class LeechingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        game_map: BaseMap,
        character: callable,
        rebuff_location: tuple[int, int] = None,
        mob_count_threshold: int = 5,
        buffs: list[str] | None = None,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        # self.game_data.update(
        #     "current_minimap_area_box",
        #     "current_minimap_position",
        #     "current_entire_minimap_box",
        #     current_map=game_map,
        #     current_minimap=game_map.minimap,
        #     current_mobs=game_map.mobs,
        #     character=character(),
        # )

        self._training_skill = self.game_data.character.skills[
            self.game_data.character.main_skill
        ]
        self._teleport_skill = self.game_data.character.skills["Teleport"]
        # self.game_data.current_minimap.generate_grid_template(allow_teleport=True)
        self._mob_count_threshold = mob_count_threshold
        if buffs:
            self._buffs_to_use = [
                self.game_data.character.skills[buff] for buff in buffs
            ]
        else:
            self._buffs_to_use = []
        for skill in self.game_data.character.skills.values():
            if (
                skill.type in ["Buff", "Party Buff"]
                and skill.use_by_default
                and skill not in self._buffs_to_use
            ):
                self._buffs_to_use.append(skill)

        if rebuff_location:
            self._rebuff_location = rebuff_location
        else:
            self._rebuff_location = self.game_data.current_minimap.central_node

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    @property
    def items_to_monitor(self) -> list[DecisionGenerator]:
        generators = []
        for skill in self.game_data.character.skills.values():
            if skill.type in ["Buff"] and skill in self._buffs_to_use:
                generators.append(Rebuff(self.game_data, skill))
        generators.append(PetFood(self.game_data))
        return generators

    @property
    def next_map_rotation(self) -> DecisionGenerator:
        buffs = []
        for skill in self.game_data.character.skills.values():
            if skill.type in ["Party Buff"] and skill in self._buffs_to_use:
                buffs.append(skill)
        return [
            TelecastRotationGenerator(
                self.game_data,
                self.rotation_lock,
                teleport_skill=self._teleport_skill,
                ultimate=self._training_skill,
                mob_threshold=self._mob_count_threshold,
            ),
            LocalizedRebuff(
                self.game_data,
                self.rotation_lock,
                self._teleport_skill,
                buffs,
                self._rebuff_location,
            ),
        ]

    @property
    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return [
            MobCheck(self.game_data, time_threshold=10, mob_threshold=3),
        ]
