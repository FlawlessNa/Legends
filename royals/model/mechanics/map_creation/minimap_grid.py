import math
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
    JUMP = 4
    FALL_LEFT = 5
    FALL_RIGHT = 6
    FALL_ANY = 7
    IN_MAP_PORTAL = 8
    OUT_MAP_PORTAL = 9
    TELEPORT_LEFT = 10
    TELEPORT_RIGHT = 11
    TELEPORT_UP = 12
    TELEPORT_DOWN = 13
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
    connections_types: list[ConnectionTypes] = field(default_factory=list, init=False)
    grid_hash: int = field(default=None)

    def __hash__(self) -> int:
        """
        A node is uniquely identified by its coordinates, characteristics and the grid
        in which it belongs. The grid is identified by its hash, not by its name, because
        the same grid can be re-created with various configurations.
        """
        return hash((self.x, self.y, self.walkable, self.weight, self.grid_hash))

    def __eq__(self, other: "MinimapNode") -> bool:
        return isinstance(other, MinimapNode) and (
            self.x == other.x
            and self.y == other.y
            and self.walkable == other.walkable
            and self.weight == other.weight
            and self.grid_hash == other.grid_hash
        )

    # noinspection PyMethodOverriding
    def connect(
        self, other: "MinimapNode", connection_type: ConnectionTypes
    ) -> None:  # noqa
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

    def get_connection_type(self, other: "MinimapNode") -> ConnectionTypes:
        """
        Returns the connection type between this node and the other.
        """
        num_connections = self.connections.count(other)
        if num_connections == 1:
            return self.connections_types[self.connections.index(other)]
        elif num_connections == 2:
            # Check that the two types of connections are JUMP and corresponding TELEPORT
            # If so, retain the TELEPORT.
            connections = [
                type_ for conn, type_ in zip(self.connections, self.connections_types)
                if conn == other
            ]
            if (
                ConnectionTypes.JUMP in connections
                and ConnectionTypes.TELEPORT_UP in connections
            ):
                return ConnectionTypes.TELEPORT_UP
            elif (
                ConnectionTypes.JUMP_DOWN in connections
                and ConnectionTypes.TELEPORT_DOWN in connections
            ):
                return ConnectionTypes.TELEPORT_DOWN
            else:
                breakpoint()
                raise NotImplementedError
        else:
            breakpoint()
            raise NotImplementedError


class MinimapGrid(Grid):
    """
    Wrapper around Grid that replaces all GridNodes with MinimapNodes.
    """
    ALL_DIAGONAL_NEIGHBORS = 1
    NO_DIAGONAL_NEIGHBORS = 2

    nodes: list[list[MinimapNode]]

    def __init__(
        self,
        canvas: np.ndarray,
        speed: float,
        grid_id: str = None,
        portal_cost_reduction: float = 0.9,
        teleport_cost_reduction: float = 0.5,
        jump_down_cost_reduction: float = 0.1,
    ):
        super().__init__(matrix=canvas, grid_id=grid_id)
        self.grid_id = grid_id
        self._replace_nodes()
        self.speed = speed
        self.portal_cost_reduction = portal_cost_reduction
        self.teleport_cost_reduction = teleport_cost_reduction
        self.jump_down_cost_reduction = jump_down_cost_reduction

    @property
    def cost_reduction(self) -> dict:
        return {
            ConnectionTypes.IN_MAP_PORTAL: self.portal_cost_reduction,
            ConnectionTypes.TELEPORT_LEFT: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_RIGHT: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_UP: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_DOWN: self.teleport_cost_reduction,
            ConnectionTypes.JUMP_DOWN: self.jump_down_cost_reduction
        }

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
                    node.connections or list(),
                    grid_hash=hash(self)
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

    def calc_cost(self, node_a: MinimapNode, node_b: MinimapNode, weighted=True) -> float:
        """
        Returns the cost of moving from node_a to node_b.
        """
        ng = super().calc_cost(node_a, node_b, False)
        if node_b in node_a.connections:
            connection_type = node_a.get_connection_type(node_b)
            dist = math.dist((node_a.x, node_a.y), (node_b.x, node_b.y))
            reduce_by = self.cost_reduction.get(connection_type, 0)
            ng += dist * (1 - reduce_by)

        if weighted:
            ng *= node_b.weight
        return ng

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
