import time
import multiprocessing.managers

from botting.core.botv2.action_data import ActionRequest
from botting.core.botv2.decision_maker import DecisionMaker
from botting.core.botv2.bot_data import BotData
from botting.utilities import config_reader

from royals.game_data import RotationData
from royals.models_implementations import RoyalsSkill


class Rotation(DecisionMaker):
    _type = "Rotation"
