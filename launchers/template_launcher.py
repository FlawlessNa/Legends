from core.session_manager import SessionManager
from core.controller import Controller
import asyncio


def dummy_coroutine():
    async def _test():
        print('Async test before sleep')
        await asyncio.sleep(10)
        print("Async test after sleep")
        raise Exception('Test exception')
    # asyncio.run(controller.move('right', 5, True))
    asyncio.run(_test())

if __name__ == '__main__':
    from functools import partial
    from core.botprocess import BotProcess
    handle = 0x001A05F2
    test = BotProcess(handle, 'FarmFest1')

    # test_f = partial(dummy_coroutine, test)
    with SessionManager(test) as session:
        session.start()
