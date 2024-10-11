from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathfinding.core.grid import Grid, DiagonalMovement
from pathfinding.core.node import GridNode

from botting.utilities import Box


class ConnectionTypes(Enum):
    """
    Enum to hold the different types of connections nodes.
    """
    JUMP_DOWN = 1
    JUMP_LEFT = 2
    JUMP_RIGHT = 3
    JUMP_UP = 4
    FALL_LEFT = 5
    FALL_RIGHT = 6
    FALL_ANY = 7
    JUMP_LEFT_AND_UP = 8
    JUMP_RIGHT_AND_UP = 9
    IN_MAP_PORTAL = 10
    OUT_MAP_PORTAL = 11
    TELEPORT_LEFT = 12
    TELEPORT_RIGHT = 13
    TELEPORT_UP = 14
    TELEPORT_DOWN = 15
    FLASH_JUMP_LEFT = NotImplemented
    FLASH_JUMP_RIGHT = NotImplemented
    FLASH_JUMP_LEFT_AND_UP = NotImplemented
    FLASH_JUMP_RIGHT_AND_UP = NotImplemented


@dataclass
class MinimapNode(GridNode):
    """
    Wrapper around GridNode that retains the type of connections with each node this
    one is connected to.
    """
    pass


class MinimapGrid(Grid):
    """
    Wrapper around Grid that replaces all GridNodes with MinimapNodes.
    It additionally applies MinimapEdits onto the grid, if provided.
    """
    pass


@dataclass(frozen=True, kw_only=True)
class MinimapFeature(Box):
    """
    Represents a bounding Box that groups all MinimapNodes within bounds.
    It may define specific attributes for the nodes it contains. Each node will inherit
    from those attributes unless they explicitly define their own.
    """
    offset: tuple[int, int] = field(default=(0, 0))
    walkable: bool = field(default=True)
    weight: int = field(default=1)
    avoid_staying_on_edges: bool = field(default=True)

    # Endpoints won't be connected with jumps
    no_jump_connections_from_endpoints: bool = field(default=False)


@dataclass(frozen=True)
class MinimapEdits(ABC):
    """
    Def
    """
    features: list[MinimapFeature] = field(default_factory=list)
    modified_nodes: list[MinimapNode] = field(default_factory=list)

    @abstractmethod
    def feature_cycle(self) -> list[MinimapFeature]:
        pass