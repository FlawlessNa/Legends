import asyncio
from botting.core.botv2.session_manager import SessionManager
import royals.bots as bots


def _fake_parser():
    pass


async def main():
    with SessionManager(_fake_parser) as session:
        leecher = bots.LeechingBot('WrongDoor', session.metadata)
        # mule1 = bots.TestBot('UluLoot', session.metadata)
        # mule2 = bots.TestBot('FinancialWiz', session.metadata)
        # mule3 = bots.TestBot('MoneyEngine', session.metadata)
        # mule4 = bots.TestBot('iYieldMoney', session.metadata)
        # mule5 = bots.TestBot('BCoinFarm', session.metadata)
        # await session.launch([leecher], [mule1, mule2, mule3, mule4, mule5])
        await session.launch([leecher])


if __name__ == '__main__':
    asyncio.run(main())
