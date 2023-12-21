import functools
import logging
import time

from .game_data import GameData

logger = logging.getLogger(__name__)


def failsafe_generator(max_tries: int,
                       sleep_time: float = 0,
                       response: callable = None,
                       ):
    def decorator(wrapped_generator):
        @functools.wraps(wrapped_generator)
        def wrapper_gen(*args, **kwargs):
            tries = 0
            gen = wrapped_generator(*args, **kwargs)

            game_data = args[[isinstance(arg, GameData) for arg in args].index(True)]
            handle = game_data.handle
            ign = game_data.ign
            failsafe_response = functools.partial(response, handle, ign) if response else None

            while True:
                gen_res = next(gen)
                if gen_res is False:
                    tries += 1
                    if tries >= max_tries:
                        logger.warning(
                            f"Max tries {max_tries} reached. Returning response {failsafe_response}."
                        )
                        if failsafe_response is None:
                            raise RuntimeError(
                                f"Max tries {max_tries} reached. No response given."
                            )
                        else:
                            tries = 0
                            yield failsafe_response
                    time.sleep(sleep_time)
                else:
                    tries = 0
                    yield gen_res

        return wrapper_gen
    return decorator
