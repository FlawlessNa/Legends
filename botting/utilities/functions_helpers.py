import functools
import inspect
import itertools
import random
import time
from typing import Literal


def cooldown(seconds: float):
    def decorator(func):
        last_call = [0.0]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if time.perf_counter() - last_call[0] >= seconds:
                last_call[0] = time.perf_counter()
                return func(*args, **kwargs)

        return wrapper
    return decorator


def randomize_params(
    *args,
    perc_threshold: float = 0.05,
    abs_threshold: float | None = None,
    ignore_args: str | list[str] | None = None,
    convert_args: dict[str, Literal["int", "float"]] | None = None,
    enforce_sign: bool = True,
) -> callable:
    """
    This decorator randomizes any integers, floats and Box
     that the decorated function uses parameters (default).
    If args are provided as positional string arguments, these must correspond
     to existing arguments within the decorated function.
     In such case, only these are randomized.
    :param args: If specified, these args (and no other) will be randomized.
     They must correspond to existing arguments within the decorated function.
    :param perc_threshold: default = 5%, is the margin around the parameter value.
     Parameters are randomized within that margin.
    :param abs_threshold: If specified, parameters will be randomized centered
     around +/- the absolute parameter value.
    :param ignore_args: default = None. If specified, these arguments in the
     underlying function will not be randomized.
    :param convert_args: default = None. If specified, these arguments will be
     converted to the specified type after randomization.
      Valid types are either 'int' or 'float'.
    :param enforce_sign: default = True. If True, the sign of the randomized
     value will be compared against sign of original value.
     A ValueError is raised if signs are different.
    :return: Callable with randomized arguments
    """
    if isinstance(ignore_args, str):
        ignore_args = [ignore_args]
    elif ignore_args is None:
        ignore_args = []

    if convert_args is None:
        convert_args = dict()

    def outer(func: callable) -> callable:
        @functools.wraps(func)
        def inner(*func_args, **func_kwargs):
            arguments_mapper: dict = inspect.getcallargs(
                func, *func_args, **func_kwargs
            )
            func_params = inspect.signature(func).parameters
            params_to_randomize = (
                tuple(arg for arg in args if arg not in ignore_args)
                if args
                else tuple(
                    key for key, v in arguments_mapper.items() if key not in ignore_args
                )
            )
            for arg in itertools.chain(params_to_randomize, ignore_args):
                assert (
                    arg in arguments_mapper
                ), f"The specified argument {arg} is not part of the specified keyword arguments in the underlying function {func.__qualname__}"

            if abs_threshold:
                randomized_params = {
                    k: random.uniform(v - abs_threshold, v + abs_threshold)
                    if isinstance(v, (int, float))
                    else v
                    for k, v in arguments_mapper.items()
                    if k in params_to_randomize
                }
            else:
                randomized_params = {
                    k: random.uniform(
                        v * (1 - perc_threshold), v * (1 + perc_threshold)
                    )
                    if isinstance(v, (int, float))
                    else v
                    for k, v in arguments_mapper.items()
                    if k in params_to_randomize
                }

            # For Box parameters, return a random point within their box areas instead
            randomized_params = {
                k: v.random() if hasattr(v, "random") else v
                for k, v in randomized_params.items()
            }

            if enforce_sign:
                for k, v in randomized_params.items():
                    if isinstance(v, (int, float)) and v * arguments_mapper[k] < 0:
                        raise ValueError(
                            f"The randomized value of {k} has a different sign than the original value. This is not allowed when enforce_sign=True"
                        )

            for k, v in convert_args.items():
                assert (
                    k in randomized_params.keys()
                ), f"The specified argument {k} from convert_args is not among the parameters to be randomized {params_to_randomize}."
                assert v in [
                    "int",
                    "float",
                ], f"Each val. in convert_args dict should either be equal to 'int' or 'float'"
                if v == "int" and isinstance(randomized_params[k], (int, float)):
                    randomized_params[k] = int(randomized_params[k])
                elif v == "float" and isinstance(randomized_params[k], (int, float)):
                    randomized_params[k] = float(randomized_params[k])

            arguments_mapper.update(randomized_params)
            new_args = tuple(
                arguments_mapper[arg]
                for arg in arguments_mapper
                if func_params[arg].kind == inspect.Parameter.POSITIONAL_ONLY
            )
            new_kwargs = {
                k: v
                for k, v in arguments_mapper.items()
                if not func_params[k].kind == inspect.Parameter.POSITIONAL_ONLY
            }

            # If kwargs is specified in the underlying function, it is not unpacked as part of the signature. We need to manually unpack.
            orig_kwargs = new_kwargs.pop("kwargs", {})
            new_kwargs.update(**orig_kwargs)
            return func(*new_args, **new_kwargs)

        return inner

    return outer
