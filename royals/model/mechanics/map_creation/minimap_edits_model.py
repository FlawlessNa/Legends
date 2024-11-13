import json
import numpy as np
import os
from dataclasses import asdict, dataclass, field
from paths import ROOT
from botting.utilities import Box

from .minimap_grid import MinimapGrid

_EDITS_ROOT = os.path.join(ROOT, 'royals/model/maps')


@dataclass(frozen=True, kw_only=True)
class MinimapEdits(Box):
    """
    Represents a bounding Box that groups all MinimapNodes within bounds.
    It may define specific attributes for the nodes it contains. Each node will inherit
    from those attributes unless they explicitly define their own.
    """
    name: str
    offset: tuple[int, int] = field(default=(0, 0))  # Applied to nodes within feature
    walkable: bool = field(default=True)  # To disable pathfinding through the feature

    # Higher weight = more costly to be chosen in pathfinding algorithms
    weight: int = field(default=1)

    # Random rotation points will be generated while avoiding the edges
    avoid_right_edge: bool = field(default=False)
    avoid_left_edge: bool = field(default=False)
    edge_threshold: int = field(default=0)  # Number of nodes defined as "edge"

    # Endpoints won't be connected with jump connections
    no_jump_connections_from_endpoints: bool = field(default=False)

    # If specified, the feature will be part of the rotation cycle
    rotation_indexes: list[int] = field(default_factory=list)
    relative: bool = field(default=False, init=False, repr=False)

    # def __post_init__(self):
    #     super().__post_init__()
    #     assert (
    #         self.width <= 1 or self.height <= 1
    #     ), "Minimap Features should be 1-dimensional"

    @property
    def is_platform(self) -> bool:
        return not self.is_ladder

    @property
    def is_ladder(self) -> bool:
        return 0 <= self.width <= 1

    def block_node_from_vertical_connections(self, x: int, y: int) -> bool:
        """
        Returns whether the given node should block vertical connections.
        """
        return self.no_jump_connections_from_endpoints and x in [self.left, self.right]


@dataclass(frozen=True, kw_only=True)
class AutoGeneratedFeature(MinimapEdits):
    """
    Represents a MinimapEdits feature that is automatically generated, and therefore not
    actually editing any default behaviors.
    """
    name: str
    offset: tuple = field(default=(0, 0), init=False)
    walkable: field(default=True, init=False)
    weight: int = field(default=1, init=False)
    avoid_right_edge: bool = field(default=False, init=False)
    avoid_left_edge: bool = field(default=False, init=False)
    edge_threshold: int = field(default=0, init=False)
    no_jump_connections_from_endpoints: bool = field(default=False, init=False)
    rotation_indexes: list[int] = field(default_factory=list, init=False)


@dataclass
class MinimapEditsManager:
    """
    Manages the features of a Minimap.
    """
    features: list[MinimapEdits] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.features]

    @classmethod
    def from_json(cls, map_name: str) -> "MinimapEditsManager" or None:
        """
        Load the EditsManager from a JSON file.
        """
        path = os.path.join(_EDITS_ROOT, f'{map_name}.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                features = [
                    MinimapEdits(name=name, **dct) for name, dct in data.items()
                ]
                return cls(features)

    def to_json(self, map_name: str):
        """
        Save the EditsManager to a JSON file.
        """
        features = asdict(self)['features']  # noqa
        data = {
            dct.pop('name'): dct for dct in features
        }
        data.pop('config', None)
        data.pop('relative', None)
        with open(os.path.join(_EDITS_ROOT, f'{map_name}.json'), 'w') as f:
            json.dump(data, f, indent=4)  # noqa

    def apply_grid_edits(
        self,
        raw_minimap: np.ndarray,
        apply_weights: bool = True
    ) -> np.ndarray:
        """
        Applies all feature's offset and optionally weights to the minimap.
        """
        modified = raw_minimap.copy()
        for feature in self.features:
            offset_x, offset_y = feature.offset
            vals = modified[
                feature.top:feature.bottom, feature.left:feature.right
            ].copy()
            modified[
                feature.top:feature.bottom, feature.left:feature.right
            ] = 0
            if apply_weights:
                modified[
                    feature.top + offset_y:feature.bottom + offset_y,
                    feature.left + offset_x:feature.right + offset_x
                ] = feature.weight
            else:
                modified[
                    feature.top + offset_y:feature.bottom + offset_y,
                    feature.left + offset_x:feature.right + offset_x
                ] = vals

        return modified

    def apply_pathfinding_edits(self, grid: MinimapGrid) -> MinimapGrid:
        """
        Applies all feature's walkable attribute to the grid.
        """
        pass

    def get_features_containing(self, mini_x: int, mini_y: int) -> MinimapEdits | None:
        """
        Returns the features that contain the given coordinates.
        """
        vals = [
            feature for feature in self.features
            if feature.left <= mini_x <= feature.right
            and feature.top <= mini_y <= feature.bottom
        ]
        assert len(vals) <= 1, f"Multiple custom features found at {mini_x, mini_y}"
        return vals[0] if vals else None


