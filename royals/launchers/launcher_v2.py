import asyncio
from botting.core.botv2.session_manager import SessionManager
import royals.bots as bots


def _fake_parser():
    pass


async def main():
    with SessionManager(_fake_parser) as session:
        leecher = bots.TestBot('WrongDoor', session.metadata)
        mule1 = bots.TestBot('UluLoot', session.metadata)
        mule2 = bots.TestBot('FinancialWiz', session.metadata)
        await session.launch([leecher], [mule1, mule2])


if __name__ == '__main__':
    asyncio.run(main())
