import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseCharacter, BaseMob


def get_all_annotations(class_: type) -> dict:
    annotations = class_.__annotations__
    for base in class_.__bases__:
        if base is not object:
            annotations.update(get_all_annotations(base))
    return annotations


@dataclass
class GameData(ABC):
    """
    Base class used as a data container that is shared among all generators.
    Generators can use this class to store and retrieve data, as well as update it.
    Engines should update the current_loop_id upon every loop iteration. This is used
    as a mechanism to prevent attributes from being updated multiple times in the same
    iteration. Note that this only works with the update method, and for positional
    arguments only (NOT for keywords-arguments).

    Sample data attributes are defined below.
    """

    handle: int = field(repr=False)
    ign: str = field()
    character: BaseCharacter = field(default=None)
    current_map: BaseMap = field(default=None)
    current_mobs: tuple[BaseMob] = field(default=None, repr=False)


    # blockers: list[str] = field(default_factory=list, repr=False, init=False)
    # blockers_types: list[str] = field(default_factory=list, repr=False, init=False)
    current_client_img: np.ndarray = field(default=None, repr=False, init=False)
    current_loop_id: float = field(repr=False, init=False, default=0.0)
    attr_update_id: dict = field(repr=False, init=False, default_factory=dict)

    def update(self, *args, **kwargs) -> None:
        """
        Generators may use this method to update any attribute that they need to use.
        QueueActions may also trigger a callback to this method upon completion or
        cancellation.
        :param args: Positional arguments that are used to update attributes.
           These arguments are only updated if the current_loop_id is different
            from the last time they were updated.
        :param kwargs: Keyword arguments that are used to update attributes.
        """
        annotations = get_all_annotations(self.__class__)
        # self._handler_blockers(kwargs)
        for k, v in kwargs.items():
            assert k in annotations or hasattr(self, k), f"Invalid attribute {k}"
            setattr(self, k, v)

        # For positional arguments, only update if the current_loop_id is different
        for arg in args:
            if self.attr_update_id.get(arg) == self.current_loop_id:
                continue

            self.attr_update_id[arg] = self.current_loop_id
            updater = self.args_dict[arg]
            setattr(self, arg, updater())

    # def create_blocker(self, name: str, generator_type: str) -> None:
    #     """
    #     Creates a boolean attribute with the given name and sets it to False.
    #     This attribute can be used to block generators from being executed.
    #     :param name: Name of the Generator that may be blocked
    #     :param generator_type: Type of generator that is being blocked.
    #     :return:
    #     """
    #     assert not hasattr(self, name), f"Attribute {name} already exists"
    #     setattr(self, name, False)
    #     self.blockers.append(name)
    #     self.blockers_types.append(generator_type)

    # def set_status(self, name: str, status: str = "Setup") -> None:
    #     """
    #     Some generators may have a status attribute used to track their progress.
    #     :param name: name of the generator.
    #     :param status: status of the generator. Defaults to "Setup" status.
    #     :return:
    #     """
    #     assert not hasattr(self, f"{name}_status"), f"Attribute {name}_status already exists"
    #     setattr(self, f"{name}_status", status)

    # def block(self, generator_type: str, excepted: str | list = None) -> None:
    #     """
    #     Blocks all generators of the given type.
    #     :param generator_type: Type of generator that is being blocked.
    #     :param excepted: Name of the generator(s) that should not be blocked.
    #     """
    #     assert generator_type in [
    #         "Rotation",
    #         "Maintenance",
    #         "AntiDetection"
    #     ], f"Invalid generator type {generator_type}"
    #
    #     for blocker in self.blockers:
    #         if generator_type == self.blockers_types[self.blockers.index(blocker)]:
    #             setattr(self, blocker, True)
    #     if excepted is not None:
    #         if isinstance(excepted, str):
    #             excepted = [excepted]
    #         for exception in excepted:
    #             setattr(self, exception, False)

    # def unblock(self, generator_type: str) -> None:
    #     """
    #     Unblocks all generators of the given type.
    #     """
    #     for blocker in self.blockers:
    #         if generator_type == self.blockers_types[self.blockers.index(blocker)]:
    #             setattr(self, blocker, False)

    # def _handler_blockers(self, kwargs: dict[str, any]) -> None:
    #     """
    #     Checks if any of the kwargs are blocking attributes.
    #     If so, update blockers accordingly.
    #     """
    #     block_rotation = kwargs.pop("block_rotation", None)
    #     block_maintenance = kwargs.pop("block_maintenance", None)
    #     block_anti_detection = kwargs.pop("block_anti_detection", None)
    #
    #     if block_rotation is not None:
    #         if block_rotation:
    #             self.block("Rotation")
    #         else:
    #             self.unblock("Rotation")
    #
    #     if block_maintenance is not None:
    #         if block_maintenance:
    #             self.block("Maintenance")
    #         else:
    #             self.unblock("Maintenance")
    #
    #     if block_anti_detection is not None:
    #         if block_anti_detection:
    #             self.block("AntiDetection")
    #         else:
    #             self.unblock("AntiDetection")

    @property
    @abstractmethod
    def args_dict(self) -> dict[str, callable]:
        """
        Use this to map *args received by "self.update" to their updating methodology.
        :return:
        """
        return {}
