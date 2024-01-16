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
    Base class to represent in-game game_data. This class is meant to be inherited by a class that will be used to store game_data about the game client.
    Here, sample game_data attributes are provided, but the inheriting class can add/remove more attributes as needed.
    """

    handle: int = field(repr=False)
    ign: str = field()
    character: BaseCharacter = field(default=None)
    current_map: BaseMap = field(default=None)
    current_mobs: tuple[BaseMob] = field(default=None, repr=False)

    blockers: list[str] = field(default_factory=list, repr=False, init=False)
    blockers_types: list[str] = field(default_factory=list, repr=False, init=False)

    def update(self, *args, **kwargs) -> None:
        """
        This method will be called whenever an in-game action is completed/cancelled. It is meant to update the game_data attributes of the class.
        It should update the relevant attributes based on the action that was completed/cancelled.
        Examples:
            If the character performed movements, then the current position (and perhaps current map) should be updated.
            If the character used a potion, then the current potion count should be updated.
            etc.
        """
        annotations = get_all_annotations(self.__class__)
        self._handler_blockers(kwargs)
        for k, v in kwargs.items():
            assert k in annotations, f"Invalid attribute {k}"
            setattr(self, k, v)

        for arg in args:
            updater = self.args_dict[arg]
            setattr(self, arg, updater())

    def create_blocker(self, name: str, generator_type: str) -> None:
        """
        Creates a boolean attribute with the given name and sets it to False.
        This attribute can be used to block generators from being executed.
        :param name: Name of the blocking attribute
        :param generator_type: Type of generator that is being blocked.
        :return:
        """
        assert not hasattr(self, name), f"Attribute {name} already exists"
        setattr(self, name, False)
        setattr(self, f"{name}_status", None)
        self.blockers.append(name)
        self.blockers_types.append(generator_type)

    def block(self, generator_type: str) -> None:
        """
        Blocks all generators of the given type.
        """
        for blocker in self.blockers:
            if generator_type == self.blockers_types[self.blockers.index(blocker)]:
                setattr(self, blocker, True)

    def unblock(self, generator_type: str) -> None:
        """
        Blocks all generators of the given type.
        """
        for blocker in self.blockers:
            if generator_type == self.blockers_types[self.blockers.index(blocker)]:
                setattr(self, blocker, False)

    def _handler_blockers(self, kwargs: dict[str, any]) -> None:
        """
        Checks if any of the kwargs are blocking attributes.
        If so, update blockers accordingly.
        """
        block_rotation = kwargs.pop("block_rotation", None)
        block_maintenance = kwargs.pop("block_maintenance", None)
        block_anti_detection = kwargs.pop("block_anti_detection", None)

        if block_rotation is not None:
            if block_rotation:
                self.block("Rotation")
            else:
                self.unblock("Rotation")

        if block_maintenance is not None:
            if block_maintenance:
                self.block("Maintenance")
            else:
                self.unblock("Maintenance")

        if block_anti_detection is not None:
            if block_anti_detection:
                self.block("AntiDetection")
            else:
                self.unblock("AntiDetection")

    @property
    @abstractmethod
    def args_dict(self) -> dict[str, callable]:
        """
        Use this to map *args received by "self.update" to their updating methodology.
        :return:
        """
        return {}
