import random
from abc import ABC, abstractmethod

from royals.utilities import Box


class BaseMap(ABC):
    @property
    @abstractmethod
    def map_features(self) -> dict[str, Box]:
        pass

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
        )
        return self.map_features[target_feature].random()

    def get_current_feature(self, current_position: tuple[float, float]) -> Box:
        """
        Returns the current platform the character is standing on.
        """
        for feature in self.map_features.values():
            if current_position in feature:
                return feature
