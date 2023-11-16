import inspect
import random
from abc import ABC

from ..mobs.base_mob import BaseMob
from royals.game_interface import InGameBaseVisuals
from royals.game_interface.dynamic_components.minimap import Minimap
from royals.utilities import Box


class BaseMap(InGameBaseVisuals, ABC):
    """
    A map contains the following:
    - A set of features, such as platforms, portals, etc.
    - A set of mobs that can be found within it (optional).
    - A set of coordinates that define the on-screen area used for detection.
    - A Minimap instance, which is fixed within that map and therefore can cache its minimap properties.
    """

    detection_box_large = Box(left=3, right=1027, top=29, bottom=725)
    detection_box_small = NotImplemented

    def __init__(
        self, handle: int, minimap: Minimap, mobs: list[BaseMob] | None = None
    ) -> None:
        super().__init__(handle)
        self.mobs = mobs
        self.minimap = minimap
        if self._large_client:
            self.detection_box = self.detection_box_large
        else:
            self.detection_box = self.detection_box_small

    @property
    def map_features(self) -> dict[str, Box]:
        if not self.__dict__:
            inspect.getmembers(self)  # Forces calculation of all properties
        return {box.name: box for box in self.__dict__.values() if isinstance(box, Box)}

    def random_point(self, feature_name: str | None = None) -> tuple[int, int]:
        """
        Returns a random point within the map.
        First, select a feature at random, weighted by its area.
        Then, select a random point within the feature.
        :return:
        """
        if feature_name is not None:
            return self.map_features[feature_name].random()

        target_feature = random.choices(
            list(self.map_features.keys()),
            weights=[feature.area for feature in self.map_features.values()],
        ).pop()
        return self.map_features[target_feature].random()

    def get_current_feature(self, current_position: tuple[float, float]) -> Box:
        """
        Returns the current platform the character is standing on.
        """
        for feature in self.map_features.values():
            if current_position in feature:
                return feature
