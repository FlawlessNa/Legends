from botting.core.botv2.session_manager import SessionManager


async def main():
    with SessionManager() as session:
        leecher = Bot(session.metadata)
        mule1 = Bot(session.metadata)
        mule2 = Bot(session.metadata)
        await session.launch([leecher], [mule1, mule2])
