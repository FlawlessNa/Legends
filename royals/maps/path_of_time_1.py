from dataclasses import dataclass

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.models_implementations.minimaps import PathOfTime1Minimap
from royals.models_implementations.mobs import PlatoonChronos


@dataclass
class PathOfTime1(BaseMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: PathOfTime1Minimap = PathOfTime1Minimap()
    mobs: tuple[BaseMob] = (
        PlatoonChronos(Box(left=0, right=1024, top=29, bottom=700)),
    )
