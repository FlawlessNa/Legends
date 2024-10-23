import json
import numpy as np
import os
from dataclasses import asdict, dataclass, field
from paths import ROOT
from botting.utilities import Box

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
    avoid_right_edge: bool = field(default=True)
    avoid_left_edge: bool = field(default=True)
    edge_threshold: int = field(default=5)  # Number of nodes defined as "edge"

    # Endpoints won't be connected with jump connections
    no_jump_connections_from_endpoints: bool = field(default=False)

    # If specified, the feature will be part of the rotation cycle
    rotation_indexes: list[int] = field(default_factory=list)
    relative: bool = field(default=False, init=False, repr=False)


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
            json.dump(data, f, indent=4)

    def apply_minimap_edits(self, raw_minimap: np.ndarray) -> np.ndarray:
        """
        Applies the walkable property of the feature onto each pixel contained within.
        Then, applies the offset to any remaining walkable node contained within.
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

            modified[
                feature.top + offset_y:feature.bottom + offset_y,
                feature.left + offset_x:feature.right + offset_x
            ] = vals

        return modified

    def apply_grid_edits(self, grid: MinimapGrid):
        pass
