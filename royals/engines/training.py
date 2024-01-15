import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator
from botting.models_abstractions import BaseMap

from royals import royals_ign_finder, RoyalsData
from .generators import (
    MobsHitting,
    SmartRotation,
    Rebuff,
    PetFood,
    MobCheck,
    DistributeAP,
)


class TrainingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        game_map: BaseMap,
        character: callable,
        training_skill: str,
        time_limit: float = 15,
        mob_count_threshold: int = 2,
        buffs: list[str] | None = None,
        teleport_enabled: bool = True,
        anti_detection_mob_threshold: int = 3,
        anti_detection_time_threshold: int = 10
    ) -> None:
        super().__init__(log_queue, bot)

        self._game_data = RoyalsData(
            self.handle,
            self.ign,
            character(),
            current_map=game_map,
            current_mobs=game_map.mobs,
            current_minimap=game_map.minimap
        )
        self._training_skill = self.game_data.get_skill(training_skill)
        if teleport_enabled:
            try:
                self._teleport_skill = self.game_data.get_skill("Teleport")
            except KeyError:
                self._teleport_skill = None
        else:
            self._teleport_skill = None

        self.game_data.update(current_minimap=self.game_data.current_map.minimap)
        self.game_data.update(
            "minimap_grid",
            allow_teleport=True if self._teleport_skill is not None else False,
        )

        self._mob_count_threshold = mob_count_threshold
        self._time_limit_central_node = time_limit
        if buffs:
            self._buffs_to_use = [
                self.game_data.get_skill(buff) for buff in buffs
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

        self._anti_detection_mob_threshold = anti_detection_mob_threshold
        self._anti_detection_time_threshold = anti_detection_time_threshold

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        generators = []
        for skill in self.game_data.character.skills.values():
            if skill.type in ["Buff", "Party Buff"] and skill in self._buffs_to_use:
                generators.append(Rebuff(self.game_data, skill))
        generators.append(PetFood(self.game_data))
        generators.append(DistributeAP(self.game_data))
        return generators

    def next_map_rotation(self) -> list[callable]:
        return [
            SmartRotation(
                self.game_data,
                self.rotation_lock,
                teleport=self._teleport_skill,
                time_limit=self._time_limit_central_node,
            ),
            MobsHitting(
                self.game_data, self._training_skill, self._mob_count_threshold
            ),
        ]

    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return [
            MobCheck(
                self.game_data,
                time_threshold=self._anti_detection_time_threshold,
                mob_threshold=self._anti_detection_mob_threshold),
        ]
