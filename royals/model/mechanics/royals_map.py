from dataclasses import dataclass, field


class RoyalsMinimap:
    """
    Draws the raw minimap from game files.
    If a minimap subclass exists for the current minimap, it loads in the specified
    modifications and modifies the raw minimap based on those.
    """


@dataclass
class RoyalsMap:
    """
    Class to hold the map of the game.
    """
    current_minimap: RoyalsMinimap = field(repr=False)