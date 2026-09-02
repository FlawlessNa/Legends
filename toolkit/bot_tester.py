import asyncio
import logging

import maple.decision_makers as dm
import maple.parsers
from botting import PARENT_LOG
from botting.core import DecisionMaker, SessionManager
from maple.bots.maple_bot import MapleBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


IGN = "StarBase"
GAME_MAP = "GhostShip1"
CHARACTER_CLASS = "Priest"


class TestBot(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        """
        Insert any decision makers you want to test here.
        """
        return [dm.Rotation]


async def test() -> None:
    with SessionManager(maple.parsers.MapleParser, debug=True) as session:
        bot = TestBot(
            IGN,
            session.metadata,
            game_map=GAME_MAP,
            character_class=CHARACTER_CLASS,
        )
        await session.launch([bot])


if __name__ == "__main__":
    asyncio.run(test())
