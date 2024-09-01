from abc import ABC
from botting.models_abstractions import BaseMob


class RoyalsMob(BaseMob, ABC):
    health_bar_color: tuple[int, int, int] = (0, 255, 0)
