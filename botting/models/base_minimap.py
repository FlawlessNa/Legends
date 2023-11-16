import inspect
import random
from abc import ABC, abstractmethod

from botting.utilities import Box
from botting.visuals import InGameDynamicVisuals


class BaseMinimap(InGameDynamicVisuals, ABC):
    """
    Example for a class representing the in-game minimap.
    This should contain the necessary methods to detect the minimap location,
    extract its title (if any), and detect the positions of characters on the minimap.
    It should also contain features found on the minimap and their coordinates.
    This lays the foundation for "random" movements while botting.
    """

    @property
    @abstractmethod
    def features(self) -> dict[str, Box]:
        """
        Returns a dictionary of all the features of the map.
        Default behavior is to return any property which returns a box, but this can be overridden.
        :return:
        """
        if not self.__dict__:
            inspect.getmembers(self)  # Forces calculation of all cached properties
        return {box.name: box for box in self.__dict__.values() if isinstance(box, Box)}

    def random_point(self, feature_name: str | None = None) -> tuple[int, int]:
        """
        Returns a random point within the minimap.
        First, select a feature at random, weighted by its area.
        Then, select a random point within the feature.
        :return:
        """
        if feature_name is not None:
            return self.features[feature_name].random()

        target_feature = random.choices(
            list(self.features.keys()),
            weights=[feature.area for feature in self.features.values()],
        ).pop()
        return self.features[target_feature].random()

    def get_current_feature(self, current_position: tuple[float, float]) -> Box:
        """
        Returns the feature in which a given position is located.
        """
        for feature in self.features.values():
            if current_position in feature:
                return feature
