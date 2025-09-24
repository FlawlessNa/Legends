import asyncio
import logging
from botting import PARENT_LOG
from botting.core import DecisionMaker, SessionManager
from maple.bots.royals_bot import MapleBot
import maple.decision_makers as dm


logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.DEBUG


IGN = 'StarBase'
BOT_CONFIGS = {
    'game_map': 'MysteriousPath3',
    'character_class': 'Priest'
}


class TestBot(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        """
        Insert any decision makers you want to test here.
        """
        return [
            dm.Rotation
        ]


async def test():
    with SessionManager(..., debug=True) as session:  # noqa
        bot = TestBot(IGN, session.metadata, **BOT_CONFIGS)
        await session.launch([bot])


if __name__ == '__main__':
    asyncio.run(test())