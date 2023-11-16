from botting.core.controls import controller

HANDLE = 0x00620DFE


async def _test_action(direction):
    await controller.move(
        HANDLE,
        "FarmFest1",
        direction,
        3,
        True,
        jump_interval=0.5,
    )
