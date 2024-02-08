from dataclasses import dataclass

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.models_implementations.minimaps import LudiFreeMarketTemplateMinimap
from .base import RoyalsMap


@dataclass
class LudiFreeMarket(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: LudiFreeMarketTemplateMinimap = LudiFreeMarketTemplateMinimap()
    mobs: tuple[BaseMob] = tuple()
