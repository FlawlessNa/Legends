import itertools
from dataclasses import dataclass, field

from botting.utilities import Box


@dataclass(frozen=True, kw_only=True)
class MinimapEdits(Box):
    """
    Represents a bounding Box that groups all MinimapNodes within bounds.
    It may define specific attributes for the nodes it contains. Each node will inherit
    from those attributes unless they explicitly define their own.
    """
    offset: tuple[int, int] = field(default=(0, 0))  # Applied to nodes within feature
    walkable: bool = field(default=True)  # To disable pathfinding through the feature

    # Higher weight = more costly to be chosen in pathfinding algorithms
    weight: int = field(default=1)

    # Random rotation points will be generated while avoiding the edges
    avoid_right_edge: bool = field(default=True)
    avoid_left_edge: bool = field(default=True)
    edge_threshold: int = field(default=5)  # Number of nodes defined as "edge"

    # Endpoints won't be connected with jump connections
    no_jump_connections_from_endpoints: bool = field(default=False)

    # If specified, the feature will be part of the rotation cycle
    rotation_indexes: list[int] = field(default_factory=list)
    relative: bool = field(default=False, init=False, repr=False)


@dataclass
class EditsManager:
    """
    Manages the features of a Minimap.
    """
    features: list[MinimapEdits] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_path: str) -> "EditsManager":
        """
        Load the EditsManager from a JSON file.
        """
        pass

    def to_json(self, json_path: str):
        """
        Save the EditsManager to a JSON file.
        """
        pass
