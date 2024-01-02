import multiprocessing

from functools import partial

from botting.core import DecisionEngine, Executor
from royals import royals_ign_finder, RoyalsData
from royals.bot_implementations.generators import rebuff
from royals.models_implementations.minimaps import MysteriousPath3
from royals.models_implementations.mobs import SelkieJr, Slimy
from .generators import smart_rotation, hit_mobs


class MysteriousPath3Training(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(self, log_queue: multiprocessing.Queue, bot: Executor, **kwargs) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.current_minimap = MysteriousPath3()
        self.game_data.current_mobs = [SelkieJr(), Slimy()]

        assert 'character_class' in kwargs, "character_class must be provided."
        assert 'training_skill' in kwargs, "training_skill must be provided."
        self.game_data.character = kwargs['character_class'](self.ign, kwargs['section'], kwargs.get('client_size', 'large'))
        self.game_data.update(
            "current_minimap_area_box",
            "current_minimap_position",
            "current_entire_minimap_box",
        )
        self._training_skill = self.game_data.character.skills[kwargs['training_skill']]
        self._teleport_skill = self.game_data.character.skills['Teleport']

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        return [
            rebuff.Rebuff(self.game_data, self.game_data.character.skills['Holy Symbol'])
        ]
          # TODO - Add a check that looks whether current node is walkable. if not walkable and static + 10s, then add some movement

    def next_map_rotation(self) -> list[callable]:
        return [
            partial(smart_rotation, self.game_data, self.watched_bot.rotation_lock, teleport=self._teleport_skill),
            partial(hit_mobs, self.game_data, self._training_skill)
        ]
