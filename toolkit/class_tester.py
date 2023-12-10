import asyncio
import math
from royals.models_implementations.minimaps.ludi_free_market_template import (
    LudiFreeMarketTemplate,
)
import numpy as np
import cv2
import time
from botting.core.controls import controller
from royals.bot_implementations.actions.random_rotation import get_to_target
from functools import partial
from typing import Literal

HANDLE = 0x009D0B92


async def _execute(act: list, current_dir: Literal["left", "right", "up", "down"]) -> None:
    try:
        if 'direction' not in act[0].keywords:
            args = (HANDLE, 'FarmFest1', current_dir)
            kwargs = act[0].keywords
            await controller.move(*args, **kwargs)
        else:
            await act[0](HANDLE, 'FarmFest1')
    except Exception as e:
        breakpoint()


if __name__ == "__main__":
    try:
        # TODO - Remaining:
        #  1. Enlarge ladder heights to make sure character always reaches top/bottom when just passing by
        #  2. When character needs to go down a ladder, they could get stuck and not enter ladder (similar to portal). Thus,
        #     try and use similar logic to portal to get character to enter ladder.
        ludi = LudiFreeMarketTemplate()
        grid = ludi.generate_grid_template()
        current_direction = 'left'
        prev_target = None
        prev_pos = None
        prev_action = None
        i = 0
        while True:
            target_pos = ludi.random_point()
            current_pos = ludi.get_character_positions(HANDLE).pop()

            while math.dist(current_pos, target_pos) > 2:
                current_pos = ludi.get_character_positions(HANDLE).pop()

                # When character hasn't moved, they may be stuck in a ladder.
                if current_pos == prev_pos:
                    i += 1
                else:
                    i = 0

                actions = get_to_target(current_pos, target_pos, ludi)
                if not actions:
                    continue

                if actions:
                    print(actions[0])
                if 'direction' in actions[0].keywords:
                    current_direction = actions[0].keywords['direction']
                if i > 3:
                    # When this happens, character is either stuck in ladder, or trying to get into one from the top.
                    # however, this could also happen if action was cancelled several times in a row.
                    # TODO - perhaps add a callback to prevent incrementing i when action is in fact cancelled.
                    if actions[0].keywords['direction'] in ['right', 'left']:
                        actions[0] = partial(actions[0].func,
                                             direction=actions[0].keywords['direction'],
                                             secondary_direction='up',
                                             duration=actions[0].keywords['duration']
                                             )
                    else:
                        actions[0] = partial(actions[0].func,
                                             direction='left' if prev_target[0] > target_pos[0] else 'right',
                                             secondary_direction=actions[0].keywords['direction'],
                                             duration=actions[0].keywords['duration']
                                             )
                    print('action changed')

                asyncio.run(
                    _execute(actions, current_direction)
                )
                prev_pos = current_pos
                prev_action = actions[0]

            prev_target = target_pos
    except Exception as e:
        breakpoint()


