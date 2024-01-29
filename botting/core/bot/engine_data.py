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
class EngineData(ABC):
    """
    Base class used as a data container that is shared among all generators.
    Generators can use this class to store and retrieve data, as well as update it.
    Engines should update the current_loop_id upon every loop iteration. This is used
    as a mechanism to prevent attributes from being updated multiple times in the same
    iteration. Note that this mechanism only works with the update method, and for
    positional arguments only (NOT for keywords-arguments).

    Sample data attributes are defined below. Child instances should define their own.
    """

    handle: int = field(repr=False)
    ign: str = field()
    character: BaseCharacter = field(default=None)
    current_map: BaseMap = field(default=None)
    current_mobs: tuple[BaseMob] = field(default=None, repr=False)

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
        if 'available_to_cast' in kwargs:
            print("available_to_cast", kwargs['available_to_cast'])
        annotations = get_all_annotations(self.__class__)
        # self._handler_blockers(kwargs)
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

    @property
    @abstractmethod
    def args_dict(self) -> dict[str, callable]:
        """
        Use this to map *args received by "self.update" to their updating methodology.
        :return:
        """
        return {}
