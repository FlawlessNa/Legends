import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseCharacter, BaseMob
from botting.utilities import get_object_by_id


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

    current_client_img: np.ndarray = field(default=None, repr=False, init=False)
    current_loop_id: float = field(repr=False, init=False, default=0.0)
    attr_update_id: dict = field(repr=False, init=False, default_factory=dict)
    generator_ids: list[int] = field(repr=False, init=False, default_factory=list)

    def add_generator_id(self, generator_id: int) -> None:
        """
        Adds a generator id to the list of generator ids.
        :param generator_id: ID of the generator.
        """
        self.generator_ids.append(generator_id)

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
        self._handler_blockers(kwargs)
        for k, v in kwargs.items():
            assert k in annotations or hasattr(self, k), f"Invalid attribute {k}"
            setattr(self, k, v)

        # For positional arguments, only update if the current_loop_id is different
        for arg in args:
            if self.attr_update_id.get(arg) == self.current_loop_id:
                print(f"Skipping {arg}")
                continue

            self.attr_update_id[arg] = self.current_loop_id
            updater = self.args_dict[arg]
            setattr(self, arg, updater())

    def block(self, generator_type: str) -> None:
        """
        Blocks all generators of the given type.
        """
        for idx in self.generator_ids:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            if gen_type == generator_type or generator_type == "All":
                setattr(generator, "blocked", True)

    def unblock(self, generator_type: str) -> None:
        """
        Unblocks all generators of the given type.
        """
        for idx in self.generator_ids:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            if gen_type == generator_type or generator_type == "All":
                setattr(generator, "blocked", False)

    def _handler_blockers(self, kwargs: dict[str, any]) -> None:
        """
        Checks if any of the kwargs are blocking attributes.
        If so, update blockers accordingly.
        """
        blocker: str = kwargs.pop('block', '')
        unblocker = kwargs.pop('unblock', '')

        if blocker:
            self.block(blocker)
        if unblocker:
            self.unblock(unblocker)

        # block_rotation = kwargs.pop("block_rotation", None)
        # block_maintenance = kwargs.pop("block_maintenance", None)
        # block_anti_detection = kwargs.pop("block_anti_detection", None)
        #
        # if block_rotation is not None:
        #     if block_rotation:
        #         self.block("Rotation")
        #     else:
        #         self.unblock("Rotation")
        #
        # if block_maintenance is not None:
        #     if block_maintenance:
        #         self.block("Maintenance")
        #     else:
        #         self.unblock("Maintenance")
        #
        # if block_anti_detection is not None:
        #     if block_anti_detection:
        #         self.block("AntiDetection")
        #     else:
        #         self.unblock("AntiDetection")

    @property
    @abstractmethod
    def args_dict(self) -> dict[str, callable]:
        """
        Use this to map *args received by "self.update" to their updating methodology.
        :return:
        """
        return {}
