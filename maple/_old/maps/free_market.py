from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from maple._old.minimaps import LudiFreeMarketTemplateMinimap
from .base import RoyalsMap


@dataclass
class LudiFreeMarket(RoyalsMap):
    minimap: LudiFreeMarketTemplateMinimap = field(
        default_factory=LudiFreeMarketTemplateMinimap
    )
    mobs: tuple[BaseMob] = field(default_factory=tuple)
