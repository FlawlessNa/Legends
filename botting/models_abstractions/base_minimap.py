import random

from abc import ABC, abstractmethod

from botting.utilities import Box
from botting.visuals import InGameBaseVisuals


class BaseMinimapFeatures(InGameBaseVisuals, ABC):
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
        Default behavior is to return any class attribute which returns a box.
        This can be overridden.
        :return:
        """
        return {
            box.name: box
            for box in self.__class__.__dict__.values()
            if isinstance(box, Box)
        }

    @property
    @abstractmethod
    def feature_cycle(self) -> list[Box]:
        """
        Returns a list of the features to be cycled through. This is used for smarter
        map rotations.
        :return:
        """
        pass

    def random_point(self, feature_name: str | None = None) -> tuple[int, int]:
        """
        Returns a random point within the minimap.
        First, select a feature at random, weighted by its area (unless specified).
        Then, select a random point within the feature.
        :return: (x, y) coordinates of the random point.
        """
        if feature_name is None:
            feature_name = random.choices(
                list(self.features.keys()),
                weights=[feature.area for feature in self.features.values()],
            ).pop()
        return self.features[feature_name].random()

    def get_feature_containing(self, position: tuple[float, float]):
        """
        Returns the feature in which a given position is located.
        """
        for feature in self.features.values():
            if position in feature:
                return feature
