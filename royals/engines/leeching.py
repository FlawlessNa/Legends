import multiprocessing

from botting.core import DecisionEngine, Executor, DecisionGenerator
from royals.maps import RoyalsMap

from royals import royals_ign_finder, RoyalsData

from .generators import (
    TelecastRotationGenerator,
    Rebuff,
    PartyRebuff,
    PetFood,
    MobCheck,
    CheckStillInMap,
    DistributeAP,
    InventoryManager,
)


class LeechingEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
        game_map: RoyalsMap,
        character: callable,
        mob_count_threshold: int,
        notifier: multiprocessing.Event,
        barrier: multiprocessing.Barrier,
        counter: multiprocessing.BoundedSemaphore,
        synchronized_buffs: list[str],
        rebuff_location: tuple[int, int] = None,
        buffs: list[str] | None = None,
        anti_detection_mob_threshold: int = 3,
        anti_detection_time_threshold: int = 10,
        num_pets: int = 1,
        inventory_management_procedure: int = InventoryManager.PROC_USE_MYSTIC_DOOR,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(
            self.handle,
            self.ign,
            character(),
            current_map=game_map,
            current_mobs=game_map.mobs,
        )

        self._training_skill = self.game_data.character.skills[
            self.game_data.character.main_skill
        ]
        self._teleport_skill = self.game_data.character.skills["Teleport"]
        self._mob_count_threshold = mob_count_threshold

        self._notifier = notifier
        self._barrier = barrier
        self._counter = counter

        self._anti_detection_mob_threshold = anti_detection_mob_threshold
        self._anti_detection_time_threshold = anti_detection_time_threshold
        self._num_pets = num_pets
        self._inventory_management_procedure = inventory_management_procedure

        self._synchronized_buffs = synchronized_buffs

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
                and skill not in self._synchronized_buffs
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
        generators = [
            InventoryManager(
                self.game_data,
                tab_to_watch="Equip",
                procedure=self._inventory_management_procedure,
            ),
            PetFood(self.game_data, num_times=self._num_pets),
            DistributeAP(self.game_data),
        ]

        for skill in self.game_data.character.skills.values():
            if skill.type == "Buff" and skill in self._buffs_to_use:
                generators.append(Rebuff(self.game_data, skill))

        generators.append(
            PartyRebuff(
                self.game_data,
                self._notifier,
                self._barrier,
                self._counter,
                self._synchronized_buffs,
                self._rebuff_location,
            )
        )
        return generators

    @property
    def next_map_rotation(self) -> DecisionGenerator:
        return TelecastRotationGenerator(
            self.game_data,
            self.rotation_lock,
            teleport_skill=self._teleport_skill,
            ultimate=self._training_skill,
            mob_threshold=self._mob_count_threshold,
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
