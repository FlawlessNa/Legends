import logging
import time
from functools import wraps

from botting import PARENT_LOG

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')


def failsafe_generator(max_tries: int,
                       sleep_time: float = 0,
                       response: callable = None):
    def decorator(wrapped_generator):
        @wraps(wrapped_generator)
        def wrapper_gen(*args, **kwargs):
            tries = 0
            gen = wrapped_generator(*args, **kwargs)
            while True:
                res = next(gen)
                if res is False:
                    tries += 1
                    if tries >= max_tries:
                        logger.warning(
                            "Max tries {max_tries} reached. Returning response {response}."
                        )
                        yield response
                    time.sleep(sleep_time)
                else:
                    tries = 0
                    yield res

        return wrapper_gen
    return decorator
