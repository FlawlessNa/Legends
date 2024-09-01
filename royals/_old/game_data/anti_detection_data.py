from dataclasses import dataclass, field

from royals._old.game_data.minimap_data import MinimapData


@dataclass
class AntiDetectionData(MinimapData):
    shut_down_at: float = field(default=None, repr=False, init=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            **super().args_dict,
        }
