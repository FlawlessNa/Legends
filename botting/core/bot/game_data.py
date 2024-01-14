from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseCharacter, BaseMob


def get_all_annotations(class_: type) -> dict:
    annotations = class_.__annotations__
    for base in class_.__bases__:
        if not base is object:
            annotations.update(get_all_annotations(base))
    return annotations


@dataclass
class GameData(ABC):
    """
    Base class to represent in-game data. This class is meant to be inherited by a class that will be used to store data about the game client.
    Here, sample data attributes are provided, but the inheriting class can add/remove more attributes as needed.
    """

    handle: int = field(repr=False)
    ign: str = field()
    character: BaseCharacter = field(default=None)
    current_map: BaseMap = field(default=None)
    current_mobs: tuple[BaseMob] = field(default=None, repr=False)

    block_rotation: bool = field(default=False, repr=False)
    block_maintenance: bool = field(default=False, repr=False)
    block_anti_detection: bool = field(default=False, repr=False)

    def update(self, *args, **kwargs) -> None:
        """
        This method will be called whenever an in-game action is completed/cancelled. It is meant to update the data attributes of the class.
        It should update the relevant attributes based on the action that was completed/cancelled.
        Examples:
            If the character performed movements, then the current position (and perhaps current map) should be updated.
            If the character used a potion, then the current potion count should be updated.
            etc.
        """
        annotations = get_all_annotations(self.__class__)
        for k, v in kwargs.items():
            assert k in annotations, f"Invalid attribute {k}"
            setattr(self, k, v)

        for arg in args:
            updater = self.args_dict[arg]
            setattr(self, arg, updater())

    @property
    @abstractmethod
    def args_dict(self) -> dict[str, callable]:
        """
        Use this to map *args received by "self.update" to their updating methodology.
        :return:
        """
        pass


import inspect
