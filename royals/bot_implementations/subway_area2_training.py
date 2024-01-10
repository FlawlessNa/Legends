import multiprocessing

from functools import partial

from botting.core import DecisionEngine, Executor
from royals import royals_ign_finder, RoyalsData
from royals.models_implementations.minimaps import KerningLine1Area2Minimap
from royals.models_implementations.mobs import JrWraith
from royals.engines.generators import random_rotation
from royals.engines.generators.rotations import hit_mobs


class SubwayTraining2(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self, log_queue: multiprocessing.Queue, bot: Executor, **kwargs
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.current_minimap = KerningLine1Area2Minimap()
        self.game_data.current_mobs = [JrWraith()]

        assert "character_class" in kwargs, "character_class must be provided."
        assert "training_skill" in kwargs, "training_skill must be provided."
        self.game_data.character = kwargs["character_class"](
            self.ign, kwargs["section"], kwargs.get("client_size", "large")
        )
        self.game_data.update(
            "current_minimap_area_box",
            "current_minimap_position",
            "current_entire_minimap_box",
        )
        self._training_skill = self.game_data.character.skills[kwargs["training_skill"]]

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        return (
            []
        )  # TODO - Add a check that looks whether current node is walkable. if not walkable and static + 10s, then add some movement

    def next_map_rotation(self) -> list[callable]:
        return [
            partial(random_rotation, self.game_data, self.watched_bot.rotation_lock),
            partial(hit_mobs, self.game_data, self._training_skill),
        ]
