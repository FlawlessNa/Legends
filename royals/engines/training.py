import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator

from royals import royals_ign_finder, RoyalsData
from royals.model.maps import RoyalsMap
from .generators import (
    SmartRotationGenerator,
    Rebuff,
    PetFood,
    MobCheck,
    DistributeAP,
    InventoryManager,
    CheckStillInMap,
    SpeedPill,
)


class TrainingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        game_map: RoyalsMap,
        character: callable,
        training_skill: str,
        time_limit: float = 15,
        mob_count_threshold: int = 2,
        buffs: list[str] | None = None,
        teleport_enabled: bool = True,
        anti_detection_mob_threshold: int = 3,
        anti_detection_time_threshold: int = 10,
        num_pets: int = 1,
        inventory_management_procedure: int = InventoryManager.PROC_DISCORD_ALERT,
    ) -> None:
        super().__init__(log_queue, bot)

        self._game_data = RoyalsData(
            self.handle,
            self.ign,
            character(),
            current_map=game_map,
            current_mobs=game_map.mobs,
        )
        self._training_skill = self.game_data.get_skill(training_skill)
        if teleport_enabled:
            try:
                self._teleport_skill = self.game_data.get_skill("Teleport")
            except KeyError:
                self._teleport_skill = None
        else:
            self._teleport_skill = None

        self._mob_count_threshold = mob_count_threshold
        self._time_limit_central_node = time_limit
        if buffs:
            self._buffs_to_use = [self.game_data.get_skill(buff) for buff in buffs]
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
        self._num_pets = num_pets
        self.inventory_management_procedure = inventory_management_procedure

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    @property
    def items_to_monitor(self) -> list[DecisionGenerator]:
        generators = [
            InventoryManager(
                self.game_data,
                tab_to_watch="Equip",
                procedure=self.inventory_management_procedure,
            ),
            PetFood(self.game_data, num_times=self._num_pets),
            SpeedPill(self.game_data),
            DistributeAP(self.game_data),
        ]
        for skill in self.game_data.character.skills.values():
            if skill.type in ["Buff", "Party Buff"] and skill in self._buffs_to_use:
                generators.append(Rebuff(self.game_data, skill))
        return generators

    @property
    def next_map_rotation(self) -> DecisionGenerator:
        return SmartRotationGenerator(
            self.game_data,
            self.rotation_lock,
            self._training_skill,
            self._mob_count_threshold,
            teleport=self._teleport_skill,
            time_limit=self._time_limit_central_node,
        )

    @property
    def anti_detection_checks(self) -> list[DecisionGenerator]:
        return [
            MobCheck(
                self.game_data,
                time_threshold=self._anti_detection_time_threshold,
                mob_threshold=self._anti_detection_mob_threshold,
            ),
            CheckStillInMap(self.game_data),
        ]
