import numpy as np
from dataclasses import dataclass, field
from enum import IntEnum
from functools import cached_property
from typing import List

from pathfinding.core.diagonal_movement import DiagonalMovement
from pathfinding.core.grid import Grid
from pathfinding.core.node import GridNode


class ConnectionTypes(IntEnum):
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
    FALL_LEFT_AND_UP = 10
    FALL_RIGHT_AND_UP = 11
    IN_MAP_PORTAL = 12
    OUT_MAP_PORTAL = 13
    TELEPORT_LEFT = 14
    TELEPORT_RIGHT = 15
    TELEPORT_UP = 16
    TELEPORT_DOWN = 17
    # FLASH_JUMP_LEFT = NotImplemented
    # FLASH_JUMP_RIGHT = NotImplemented
    # FLASH_JUMP_LEFT_AND_UP = NotImplemented
    # FLASH_JUMP_RIGHT_AND_UP = NotImplemented


@dataclass
class MinimapNode(GridNode):
    """
    Wrapper around GridNode that retains the type of connections with each node this
    one is connected to.
    """
    connections: list = field(default_factory=list)
    connections_types: list = field(default_factory=list, init=False)

    def connect(self, other: "MinimapNode", connection_type: int) -> None:  # noqa
        """
        Creates connection with another node, and retains the connection type.
        """
        super().connect(other)
        self.connections_types.append(connection_type)

    def __str__(self) -> str:
        conn_list = [
            (conn.x, conn.y, ConnectionTypes(conn_type).name)
            for conn, conn_type in zip(self.connections, self.connections_types)
        ]
        conn_str = [
            f"({x=}, {y=}, {conn_type=})" for x, y, conn_type in conn_list
        ]
        return (
            f"MinimapNode(x={self.x}, y={self.y}, walkable={self.walkable}, "
            f"weight={self.weight}, grid_id={self.grid_id}, "
            f"connections={', '.join(conn_str) or []})"
        )

    def __repr__(self) -> str:
        return str(self)


class MinimapGrid(Grid):
    """
    Wrapper around Grid that replaces all GridNodes with MinimapNodes.
    """
    ALL_DIAGONAL_NEIGHBORS = 1
    NO_DIAGONAL_NEIGHBORS = 2

    nodes: list[list[MinimapNode]]

    def __init__(self, canvas: np.ndarray, grid_id: str = None):
        super().__init__(matrix=canvas, grid_id=grid_id)
        self.grid_id = grid_id
        self._replace_nodes()

    def node(self, x, y) -> MinimapNode:
        """
        Overwrites signature to return a MinimapNode.
        """
        return self.nodes[y][x]

    def _replace_nodes(self):
        for y, row in enumerate(self.nodes):
            for x, node in enumerate(row):
                self.nodes[y][x] = MinimapNode(
                    node.x,
                    node.y,
                    node.walkable,
                    node.weight,
                    node.grid_id,
                    node.connections or list()
                )

    def neighbors(
        self, node: GridNode,
        diagonal_movement: DiagonalMovement = DiagonalMovement.never,
        include_connections: bool = True
    ) -> List[MinimapNode]:
        """
        Overwrites signature to return a list of MinimapNodes.
        Allows to exclude connections from the neighbors.
        """
        neighbors = super().neighbors(node, diagonal_movement)
        if not include_connections:
            for connection in node.connections:
                neighbors.remove(connection)
        return neighbors  # noqa

    def is_left_edge(self, node: MinimapNode) -> bool:
        neighbors = self.neighbors(
            node,
            diagonal_movement=self.ALL_DIAGONAL_NEIGHBORS,  # noqa
            include_connections=False
        )
        return not any(n.x < node.x for n in neighbors)

    def is_right_edge(self, node: MinimapNode) -> bool:
        neighbors = self.neighbors(
            node,
            diagonal_movement=self.ALL_DIAGONAL_NEIGHBORS,  # noqa
            include_connections=False
        )
        return not any(n.x > node.x for n in neighbors)

    @cached_property
    def has_portals(self) -> bool:
        return any(
            ConnectionTypes(conn) == ConnectionTypes.IN_MAP_PORTAL
            for row in self.nodes for node in row for conn in node.connections_types
        )
