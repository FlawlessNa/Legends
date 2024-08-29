from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import LudiFreeMarketTemplateMinimap
from .base import RoyalsMap


@dataclass
class LudiFreeMarket(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: LudiFreeMarketTemplateMinimap = field(
        default_factory=LudiFreeMarketTemplateMinimap
    )
    mobs: tuple[BaseMob] = tuple()
