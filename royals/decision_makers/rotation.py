import time
import multiprocessing.managers

from botting.core.botv2.action_data import ActionRequest
from botting.core.botv2.decision_maker import DecisionMaker
from botting.core.botv2.bot_data import BotData
from botting.utilities import config_reader

from royals.game_data import RotationData
from royals.models_implementations import RoyalsSkill


class BaseRotation(DecisionMaker):
    _type = "Rotation"

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: RotationData,
        training_skill: RoyalsSkill,
        mob_threshold: int,
        teleport: RoyalsSkill = None,
    ) -> None:
        super().__init__(metadata, data)
        self.training_skill = training_skill
        self.mob_threshold = mob_threshold
        self.actions = []

        self.next_target = (0, 0)
        self._teleport = teleport

        self._deadlock_counter = self._deadlock_type_2 = 0  # For Failsafe
        self._last_pos_change = time.perf_counter()  # For Failsafe
        self._prev_pos = self._prev_action = None  # For Failsafe
        self._prev_rotation_actions = []  # For Failsafe

        self._on_screen_pos = None  # For Mobs Hitting

        self._minimap_key = eval(
            config_reader("keybindings", self.data.ign, "Non Skill Keys")
        )["Minimap Toggle"]
        self.data.update(allow_teleport=True if teleport is not None else False)

    def __repr__(self) -> str:
        pass

    def _call(self, *args, **kwargs) -> ActionRequest | None:
        if getattr(self.data, "next_target", None) is not None:
            self.next_target = self.data.next_target
        else:
            self._set_next_target()
        hit_mobs = self._mobs_hitting()
        if hit_mobs:
            return hit_mobs

        return self._rotation()
