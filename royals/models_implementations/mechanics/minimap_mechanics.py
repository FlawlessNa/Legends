import numpy as np

from abc import ABC
from dataclasses import dataclass, field
from pathfinding.core.grid import Grid
from pathfinding.core.node import GridNode

from botting.models_abstractions import BaseMinimapFeatures
from botting.utilities import Box
from royals.interface import Minimap

#
# @dataclass
# class MinimapNode(GridNode):
#     """
#     Class representing a node in the pathfinding algorithm.
#     Each MinimapNode is a point within a feature the minimap.
#     Minimap Nodes have additional properties with respect to their "connections" to other nodes.
#     Their type of connection describes how the connection can be used in-game.
#     Connection types are:
#         - "jump": The character can jump from one node to another.
#         - "jump_down": The character can jump down from one node to another.
#         - "teleport": The character can teleport from one node to another.
#         - "portal": The character can use a portal from one node to another.
#     """
#
#     connections_types: list = field(default_factory=list, init=False, repr=False)
#
#     def connect(self, node: GridNode, connection_type: str = "jump_down") -> None:
#         """
#         Connects the current node to another node.
#         :param node: Node to connect to.
#         :param connection_type: The type of connection between the other node. "jump_down", "jump", "teleport", or "portal".
#         :return:
#         """
#         assert connection_type in ["jump_down", "jump", "teleport", "portal"]
#         super().connect(node)
#         self.connections_types.append(connection_type)
#


@dataclass(frozen=True, kw_only=True)
class MinimapFeature(Box):
    """
    Class representing a feature on the minimap.
    A minimap feature is essentially a box representing the platform coordinates on the minimap.
    As opposed to a Box, a MinimapFeature must have a name and either its width or its height must be equal to 0.
    MinimapFeatures establish connections with other MinimapFeatures, through the 4 types of connections.
        - Whether another platform can be jumped on
        - Whether we can jump down to another platform
        - Whether we can fall on another platform (from the edges of current platform)
        - Whether we can teleport on another platform (magician class only)
        - Whether we can use a portal to another platform and/or another map.
    Each "point" within a MinimapFeature is considered a "MinimapNode" in the pathfinding algorithm.
    """

    name: str

    # Specify name of other platform as key (string), and list of nodes that can be used
    # (or True if all nodes within feature are usable).
    jump: dict[str, list[tuple] | bool] = None
    jump_down: dict[str, list[tuple] | bool] = None
    fall: dict[str, list[tuple] | bool] = None
    teleport: dict[str, list[tuple] | bool] = None
    portal_source: dict[str, list[tuple] | bool] = None
    portal_target: dict[str, list[tuple] | bool] = None

    def __post_init__(self):
        super().__post_init__()
        assert (
            self.width == 0 or self.height == 0
        ), "Minimap Features should be 1-dimensional"
        if self.fall is not None:
            values = self.fall.values()
            if len(values) == 1:
                assert all(isinstance(val, bool) for val in values)
            elif len(values) == 2:
                for val in values:
                    assert (
                        len(val) == 1 and isinstance(val[0], tuple) and len(val[0]) == 2
                    )
                    assert val[0][0] in (self.left, self.right)
            else:
                raise ValueError(f"Invalid fall attribute for feature {self}")
        if self.portal_source is not None:
            assert all(key in self.portal_target.keys() for key in self.portal_source.keys())

    @property
    def area(self) -> int:
        """
        Overwrites default behavior and considers the axis with 0 length equal to 1 for this calculation.
        """
        return max(self.width, self.height)


class MinimapPathingMechanics(BaseMinimapFeatures, Minimap, ABC):
    @property
    def features(self) -> dict[str, MinimapFeature]:
        """
        Returns a dictionary of all the features of the map.
        This overwrites the default behavior that returns all "box" class attributes.
        :return:
        """
        return {
            feat.name: feat
            for feat in self.__class__.__dict__.values()
            if isinstance(feat, MinimapFeature)
        }

    def generate_grid_template(self, handle: int) -> Grid:
        """
        Generates a "grid"-like array of the minimap, which includes royals mechanics.
        Those mechanics are:
            - Connect nodes between parallel, horizontal platforms, provided they are not too distant (jump down).
            - Connect adjacent nodes with small gaps (jump and/or teleport), provided they are not too distant.
            - Connect nodes between teleporters (can be one-way or two-way).
            - Connect nodes between portals (can be one-way or two-way) # TODO
        :param handle: Handle to the game window.
        :return: Grid object
        """
        width, height = self.map_area_width, self.map_area_height
        if isinstance(width, type(NotImplemented)) or isinstance(
            height, type(NotImplemented)
        ):
            map_area = self.get_map_area_box(handle)
            width, height = map_area.width, map_area.height

        canvas = np.zeros((height, width), dtype=np.uint8)
        canvas = self._preprocess_img(canvas)

        base_grid = Grid(matrix=canvas)
        self._add_jumps(base_grid)
        self._add_jump_downs(base_grid)
        self._add_portals(base_grid)

        return base_grid

    def _add_jumps(self, grid: Grid) -> None:
        for feature in self.features.values():
            if feature.jump is None:
                continue

            for key in feature.jump:
                other_feature = self.features[key]
                if feature.width == other_feature.width == 0:
                    self._add_jump_from_ladder_to_ladder(grid, feature, other_feature)
                elif feature.width == 0:
                    self._add_jump_out_of_ladder(grid, feature, other_feature)
                elif other_feature.width == 0:
                    self._add_jump_into_ladder(grid, feature, other_feature)
                else:
                    self._add_horizontal_jump(grid, feature, other_feature)

    @staticmethod
    def _add_horizontal_jump(
        grid: Grid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        """
        Used to connect nodes from horizontal minimap features.
        """
        nodes = feature.jump[other_feature.name]
        nodes = (
            [(i, feature.top) for i in range(feature.left, feature.right + 1)]
            if nodes is True
            else nodes
        )
        for node in nodes:
            # Platforms are overlapping, in which case the connection is assumed upwards
            if node[0] in range(other_feature.left, other_feature.right + 1):
                grid.node(*node).connect(grid.node(node[0], other_feature.top))

            # Target is to the right, in which case the connection is made to the leftmost node
            elif node[0] < other_feature.left:
                grid.node(*node).connect(
                    grid.node(other_feature.left, other_feature.top)
                )

            # Target is to the left, in which case the connection is made to the rightmost node
            elif node[0] > other_feature.right:
                grid.node(*node).connect(
                    grid.node(other_feature.right, other_feature.top)
                )

    def _add_jump_from_ladder_to_ladder(
        self, grid: Grid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        raise NotImplementedError

    def _add_jump_out_of_ladder(
        self, grid: Grid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        raise NotImplementedError

    def _add_jump_into_ladder(
        self, grid: Grid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        raise NotImplementedError

    def _add_jump_downs(
        self,
        grid: Grid,
    ) -> None:
        """
        Adds connections between each node specified for "jump down" movements.
        :param grid: Grid to add connections to
        """
        for feature in self.features.values():
            if feature.jump_down is None:
                continue

            for key, val in feature.jump_down.items():
                other_feature = self.features[key]
                nodes = (
                    [(i, feature.top) for i in range(feature.left, feature.right + 1)]
                    if val is True
                    else val
                )
                for node in nodes:
                    assert grid.node(
                        node[0], other_feature.top
                    ).walkable, f"Error in defining jump down for {feature}. Not all nodes in {other_feature} are walkable."
                    grid.node(*node).connect(grid.node(node[0], other_feature.top))

    def _add_portals(self, grid: Grid) -> None:
        """
        Adds connections between nodes into the grid based on portals in-game.
        """
        for feature in self.features.values():
            if feature.portal_source is None:
                continue

            for key, val in feature.portal_source.items():
                nodes = (
                    [(i, feature.top) for i in range(feature.left, feature.right + 1)]
                    if val is True
                    else val
                )
                target = feature.portal_target[key]
                if target is None:
                    continue
                assert len(target) == 1
                for node in nodes:
                    grid.node(*node).connect(grid.node(*target[0]))