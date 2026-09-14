from .calibration import CalibrationBot
from .leech_mule import LeechMuleWithBuffs, LeechMuleWithoutBuffs
from .leeching import LeechingBot
from .training import TrainingBot

# The registry `maple.launchers.run` builds its `bot:` lookup from, by inspection.
# Explicit because these imports exist only to re-export.
__all__ = [
    "CalibrationBot",
    "LeechMuleWithBuffs",
    "LeechMuleWithoutBuffs",
    "LeechingBot",
    "TrainingBot",
]
