"""
The mobs the Bot's map spawns, as its detection looks for them.
"""

from collections.abc import Sequence
from typing import Any

from botting.core import Key, Provider
from botting.models_abstractions import BaseMob
from maple.model.mechanics.maple_mob import MapleMob


class MobsProvider(Provider):
    """
    Serves `MOBS`: a mob class for each of the map's spawns, by its detection
    class name (`maple.bots.map_mobs`).

    Bot-level: the Bot knows the map's mobs, and has checked a model detects
    them, before it builds this Provider.
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        detection_classes: Sequence[str] = (),
        **settings: object,
    ) -> None:
        """
        :param detection_classes: The detection class names of the map's mobs,
            in the order the map lists them.
        """
        super().__init__(*args, **settings)
        self.detection_classes = tuple(detection_classes)

    def setup(self) -> None:
        self.register(MOBS, self._mobs)

    def _mobs(self) -> tuple[BaseMob, ...]:
        return tuple(MapleMob(name) for name in self.detection_classes)


#: The map's mobs, one class per detection class name. Made once, at start.
MOBS: Key[tuple[BaseMob, ...]] = Key("mobs", MobsProvider)
