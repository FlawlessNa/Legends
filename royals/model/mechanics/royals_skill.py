import cv2
import numpy as np
import os
from dataclasses import dataclass, field

from paths import ROOT
from botting.models_abstractions import Skill

MATCH_TEMPLATE_THRESHOLD = 0.55
MATCH_ICON_THRESHOLD = 0.75


@dataclass(frozen=True)
class RoyalsSkill(Skill):
    """
    Adds an icon property to the Skill class, which is used to detect if skill cast
    was successful. Only applies for Buff-type skills.
    """

    icon_path: str = field(
        init=False,
        repr=False,
        default=os.path.join(ROOT, f"royals/assets/detection_images"),
    )
    vertical_up_screen_range: int = field(default=None, repr=False)
    vertical_down_screen_range: int = field(default=None, repr=False)

    @property
    def icon(self) -> np.ndarray:
        return cv2.imread(os.path.join(self.icon_path, f"{self.name}.png"))


@dataclass(frozen=True)
class RoyalsBuff(RoyalsSkill):
    """
    Specialization for Buffs that includes parameters to confirm whether a buff was
    properly cast by attempting to match the buff icon in the top-right corner of in-
    game screen.
    """
    type: str = field(init=False, default="Buff")
    match_template_threshold: float = field(default=MATCH_TEMPLATE_THRESHOLD)
    match_icon_threshold: float = field(default=MATCH_ICON_THRESHOLD)


@dataclass(frozen=True)
class RoyalsPartyBuff(RoyalsSkill):
    """
    Specialization for Buffs that includes parameters to confirm whether a buff was
    properly cast by attempting to match the buff icon in the top-right corner of in-
    game screen.
    """
    type: str = field(init=False, default="Party Buff")
    match_template_threshold: float = field(default=MATCH_TEMPLATE_THRESHOLD)
    match_icon_threshold: float = field(default=MATCH_ICON_THRESHOLD)
