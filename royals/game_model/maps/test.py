from .base_map import BaseMap

from royals.utilities import Box


class TestMap(BaseMap):

    @property
    def map_features(self) -> dict[str, Box]:
        return {
            'Dummy Feature': self.dummy_feature
        }

    @property
    def dummy_feature(self) -> Box:
        return Box(offset=True, left=99, right=113, top=52, bottom=53)
