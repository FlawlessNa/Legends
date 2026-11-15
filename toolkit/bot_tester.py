"""
Run one MapleBot with the Decision Makers you list, to test them live.

Run it when you want a Session with a hand-picked set of Decision Makers
(`TestBot._decision_makers`, now just `Rotation`) instead of the full
launcher (`maple/launchers/run.py`). Edit `IGN`, `MAP` and `CHARACTER_CLASS`
at the top first.

    python -m toolkit.bot_tester

Needs the MapleStory client open on that character, with Discord set up as the
launcher needs it (`configs/discord.ini`). **It sends input to the game**: the
Decision Makers drive the character, in debug mode. Stop it with the Session's
stop file.
"""

import asyncio
import logging

import maple.decision_makers as dm
import maple.parsers
from botting import PARENT_LOG
from botting.core import DecisionMaker, SessionManager
from maple.bots.maple_bot import MapleBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


IGN = "StarBase"
MAP = "auto"
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
            map=MAP,
            character_class=CHARACTER_CLASS,
        )
        await session.launch([bot])


if __name__ == "__main__":
    asyncio.run(test())
