import math
from dataclasses import dataclass, field
from enum import IntEnum
from functools import cached_property
from typing import cast

import numpy as np
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
    grid_hash: int | None = field(default=None)

    def __hash__(self) -> int:
        """
        A node is uniquely identified by its coordinates, characteristics and the grid
        in which it belongs. The grid is identified by its hash, not by its name, because
        the same grid can be re-created with various configurations.
        """
        return hash((self.x, self.y, self.walkable, self.weight, self.grid_hash))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MinimapNode) and (
            self.x == other.x
            and self.y == other.y
            and self.walkable == other.walkable
            and self.weight == other.weight
            and self.grid_hash == other.grid_hash
        )

    # noinspection PyMethodOverriding
    def connect(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, other_node: MinimapNode, connection_type: ConnectionTypes
    ) -> None:
        """
        Creates connection with another node, and retains the connection type.

        Deliberately incompatible with `GridNode.connect`, which takes no connection
        type: a `MinimapNode` connection that does not say *how* it is traversed
        cannot be compiled into a movement. Every call site is in `maple_map.py` and
        passes one. Suppressed rather than fixed — giving `connection_type` a default
        would satisfy the checker by letting a caller create the untyped connection
        this signature exists to forbid.
        """
        super().connect(other_node)
        self.connections_types.append(connection_type)

    def __str__(self) -> str:
        conn_list = [
            (conn.x, conn.y, ConnectionTypes(conn_type).name)
            for conn, conn_type in zip(self.connections, self.connections_types)
        ]
        conn_str = [f"({x=}, {y=}, {conn_type=})" for x, y, conn_type in conn_list]
        return (
            f"MinimapNode(x={self.x}, y={self.y}, walkable={self.walkable}, "
            f"weight={self.weight}, grid_id={self.grid_id}, "
            f"connections={', '.join(conn_str) or []})"
        )

    def __repr__(self) -> str:
        return str(self)

    def get_connection_type(self, other: MinimapNode) -> ConnectionTypes:
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
                type_
                for conn, type_ in zip(self.connections, self.connections_types)
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
                raise NotImplementedError
        else:
            raise NotImplementedError


class MinimapGrid(Grid):
    """
    Wrapper around Grid that replaces all GridNodes with MinimapNodes.
    """

    nodes: list[list[MinimapNode]]

    def __init__(
        self,
        canvas: np.ndarray,
        speed: float,
        grid_id: str | None = None,
        portal_cost_reduction: float = 0.8,
        teleport_cost_reduction: float = 0.6,
        jump_down_cost_reduction: float = 0.7,
        portal_overhead: float = 1.0,
        teleport_overhead: float = 2.0,
        jump_down_overhead: float = 3.0,
    ) -> None:
        super().__init__(matrix=canvas, grid_id=grid_id)
        self.grid_id = grid_id
        self._replace_nodes()
        self.speed = speed
        self.portal_cost_reduction = portal_cost_reduction
        self.teleport_cost_reduction = teleport_cost_reduction
        self.jump_down_cost_reduction = jump_down_cost_reduction
        self.portal_overhead = portal_overhead
        self.teleport_overhead = teleport_overhead
        self.jump_down_overhead = jump_down_overhead

    @property
    def cost_reduction(self) -> dict:
        return {
            ConnectionTypes.IN_MAP_PORTAL: self.portal_cost_reduction,
            ConnectionTypes.TELEPORT_LEFT: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_RIGHT: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_UP: self.teleport_cost_reduction,
            ConnectionTypes.TELEPORT_DOWN: self.teleport_cost_reduction,
            ConnectionTypes.JUMP_DOWN: self.jump_down_cost_reduction,
        }

    @property
    def connection_overhead(self) -> dict:
        return {
            ConnectionTypes.IN_MAP_PORTAL: self.portal_overhead,
            ConnectionTypes.TELEPORT_LEFT: self.teleport_overhead,
            ConnectionTypes.TELEPORT_RIGHT: self.teleport_overhead,
            ConnectionTypes.TELEPORT_UP: self.teleport_overhead,
            ConnectionTypes.TELEPORT_DOWN: self.teleport_overhead,
            ConnectionTypes.JUMP_DOWN: self.jump_down_overhead,
        }

    def node(self, x: int, y: int) -> MinimapNode:
        """
        Overwrites signature to return a MinimapNode.
        """
        return self.nodes[y][x]

    def _replace_nodes(self) -> None:
        """
        Rebuilds every GridNode as a MinimapNode.

        Keywords are load-bearing: `GridNode`'s first eight dataclass fields are the
        pathfinder's scratch state (h, g, f, opened, closed, parent, retain_count,
        tested), so positional arguments land the coordinates there and leave every
        node on its defaults (x=0, y=0, grid_id=None). `__post_init__` then calls
        `cleanup()`, which wipes the misplaced values, so the loss is silent.
        """
        for y, row in enumerate(self.nodes):
            for x, node in enumerate(row):
                self.nodes[y][x] = MinimapNode(
                    x=node.x,
                    y=node.y,
                    walkable=node.walkable,
                    weight=node.weight,
                    grid_id=node.grid_id,
                    connections=node.connections or [],
                    grid_hash=hash(self),
                )

    def adjacent_nodes(
        self, node: GridNode, diagonal: bool = False
    ) -> list[MinimapNode]:
        """
        The cells physically touching `node` on the canvas, connections excluded.

        A separate question from the one `neighbors` answers, which is the
        pathfinder's: every node reachable from here in one step, connections
        included. That one is left to the base class untouched. This one is
        geometric — which cells *touch* this one — and `diagonal` widens "touch"
        from the four orthogonal cells to all eight.

        `DiagonalMovement` stays inside this file. Its members are plain `int`s on a
        plain class that annotates itself as if it were an enum, so no value of the
        declared type exists and any caller passing one is a type error; exposing a
        `bool` keeps that unsatisfiable annotation off this class's interface.
        """
        movement = DiagonalMovement.always if diagonal else DiagonalMovement.never
        neighbors = super().neighbors(
            node,
            movement,  # pyright: ignore[reportArgumentType]
        )
        if node.connections:
            exclude = {id(c) for c in node.connections}
            neighbors = [n for n in neighbors if id(n) not in exclude]
        # `_replace_nodes` rebuilds every entry of `self.nodes` as a `MinimapNode`,
        # and with connections dropped every neighbour is drawn from there.
        return cast("list[MinimapNode]", neighbors)

    def calc_cost(
        self, node_a: MinimapNode, node_b: MinimapNode, weighted: bool = True
    ) -> float:
        """
        Returns the cost of moving from node_a to node_b.
        """
        ng = super().calc_cost(node_a, node_b, False)
        if node_b in node_a.connections:
            connection_type = node_a.get_connection_type(node_b)
            if connection_type in (
                ConnectionTypes.JUMP_RIGHT,
                ConnectionTypes.JUMP_LEFT,
            ):
                dist = abs(node_a.x - node_b.x)
            else:
                dist = math.dist((node_a.x, node_a.y), (node_b.x, node_b.y))
            reduce_by = self.cost_reduction.get(connection_type, 0)
            overhead = self.connection_overhead.get(connection_type, 0)
            ng = overhead + dist * (1 - reduce_by)

        if weighted:
            ng *= node_b.weight
        return ng

    def is_left_edge(self, node: MinimapNode) -> bool:
        neighbors = self.adjacent_nodes(node, diagonal=True)
        return not any(n.x < node.x for n in neighbors)

    def is_right_edge(self, node: MinimapNode) -> bool:
        neighbors = self.adjacent_nodes(node, diagonal=True)
        return not any(n.x > node.x for n in neighbors)

    @cached_property
    def has_portals(self) -> bool:
        return any(
            ConnectionTypes(conn) == ConnectionTypes.IN_MAP_PORTAL
            for row in self.nodes
            for node in row
            for conn in node.connections_types
        )
