import pytest

from botting.utilities import randomize_params, Box


def _test_function1(
    a: str = "5",
    b: int = 10,
    c: float = 15.0,
    *,
    kw_a: str = "5",
    kw_b: int = 10,
    kw_c: float = 15.0,
) -> dict:
    """Some arguments are forced to be called as keyword arguments by the underlying function."""
    return {"a": a, "b": b, "c": c, "kw_a": kw_a, "kw_b": kw_b, "kw_c": kw_c}


def _test_function2(
    a: str = "5",
    b: int = 10,
    c: float = 15.0,
    /,
    *,
    kw_a: str = "5",
    kw_b: int = 10,
    kw_c: float = 15.0,
) -> dict:
    """Some arguments are forced to be called as positional and others as keyword arguments by the underlying function."""
    return {"a": a, "b": b, "c": c, "kw_a": kw_a, "kw_b": kw_b, "kw_c": kw_c}


def _test_function3(
    a: str = "5",
    b: int = 10,
    c: float = 15.0,
    /,
    kw_a: str = "5",
    kw_b: int = 10,
    kw_c: float = 15.0,
) -> dict:
    """Some arguments are forced to be called as positional arguments by the underlying function."""
    return {"a": a, "b": b, "c": c, "kw_a": kw_a, "kw_b": kw_b, "kw_c": kw_c}


def _test_function4(
    a: str = "5",
    b: int = 10,
    c: float = 15.0,
    kw_a: str = "5",
    kw_b: int = 10,
    kw_c: float = 15.0,
) -> dict:
    """All arguments are freeform."""
    return {"a": a, "b": b, "c": c, "kw_a": kw_a, "kw_b": kw_b, "kw_c": kw_c}


def _standard_comparison(
    actuals,
    randomized,
    *,
    perc_threshold: float = 0.05,
    randomized_keys: list[tuple] | None = None,
) -> None:
    if randomized_keys is None:
        randomized_keys = [tuple(actual.keys()) for actual in actuals]
    for act, rand, rand_keys in zip(actuals, randomized, randomized_keys):
        assert act.keys() == rand.keys()
        for key in act.keys():
            if isinstance(act[key], (int, float)) and key in rand_keys:
                assert (
                    rand[key] * (1 - perc_threshold)
                    <= act[key]
                    <= rand[key] * (1 + perc_threshold)
                )
            elif isinstance(act[key], Box) and key in rand_keys:
                assert rand[key] in act[key]
            else:
                assert act[key] == rand[key]


def test_randomize_params():
    defaults = [
        _test_function1(),
        _test_function2(),
        _test_function3(),
        _test_function4(),
    ]

    for i in range(1000):
        # Testing that defaults are randomized if no parameters are specified for both randomize_args and the underlying function
        res = [
            randomize_params()(_test_function1)(),
            randomize_params()(_test_function2)(),
            randomize_params()(_test_function3)(),
            randomize_params()(_test_function4)(),
        ]
        _standard_comparison(res, defaults)

        # Testing that assert is raised when arguments specified into randomize_args are not specified in the underlying function
        with pytest.raises(AssertionError):
            randomize_params("d")(_test_function1)("a", 10, 15.2)
        with pytest.raises(AssertionError):
            randomize_params("d")(_test_function2)("a", 10, 15.2)
        with pytest.raises(AssertionError):
            randomize_params("d")(_test_function3)("a", 10, 15.2)
        with pytest.raises(AssertionError):
            randomize_params("d")(_test_function4)("a", 10, 15.2)

        # Testing that only specified params are randomized, and within expected range. Other params are left untouched.
        res = [
            randomize_params("c", "kw_c")(_test_function1)(b=10, kw_b=10),
            randomize_params("c", "kw_c")(_test_function2)("5", 10, kw_b=10, kw_c=15.0),
            randomize_params("kw_c")(_test_function3)(kw_c=15.0),
            randomize_params("kw_a")(_test_function4)(c=15.0),
        ]
        keys = [("c", "kw_c"), ("c", "kw_c"), ("kw_c",), ("kw_a",)]
        _standard_comparison(res, defaults, randomized_keys=keys)

        # Testing that ignore_args works properly
        res = [
            randomize_params(ignore_args=["b", "c"])(_test_function1)(
                a="5", b=10, kw_b=10
            ),
            randomize_params("c", ignore_args="kw_c")(_test_function2)(
                "5", 10, kw_b=10, kw_c=15.0
            ),
            randomize_params("kw_c", ignore_args="kw_c")(_test_function3)(
                "5", 10, kw_c=15.0
            ),
            randomize_params("b", "c", "kw_b", ignore_args="kw_c")(_test_function4)(
                c=15.0
            ),
        ]
        keys = [("a", "kw_a", "kw_b", "kw_c"), ("c",), tuple(), ("b", "c", "kw_b")]
        _standard_comparison(res, defaults, randomized_keys=keys)

        # Nothing should happen when convert_args is specified but the requested args to randomize are not (int, float, Box)
        assert (
            randomize_params("kw_a", convert_args={"kw_a": "int"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )
            == _test_function1()
        )
        assert isinstance(
            randomize_params("kw_a", convert_args={"kw_a": "int"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )["kw_a"],
            str,
        )

        assert isinstance(
            randomize_params("kw_b", convert_args={"kw_b": "int"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )["kw_b"],
            int,
        )
        assert isinstance(
            randomize_params("kw_b", convert_args={"kw_b": "float"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )["kw_b"],
            float,
        )
        assert isinstance(
            randomize_params(convert_args={"kw_c": "int"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )["kw_c"],
            int,
        )
        assert isinstance(
            randomize_params(convert_args={"kw_c": "float"})(_test_function1)(
                kw_a="5", kw_b=10, kw_c=15.0
            )["kw_b"],
            float,
        )

        # Testing that enforce_sign works properly
        assert (
            -115
            <= randomize_params(abs_threshold=100, enforce_sign=False)(_test_function1)(
                kw_a="5", kw_b=10, kw_c=-15.0
            )["kw_c"]
            <= 85
        )
        try:
            assert (
                -115
                <= randomize_params(abs_threshold=100, enforce_sign=True)(
                    _test_function1
                )(kw_a="5", kw_b=10, kw_c=-15.0)["kw_c"]
                <= 85
            )
        except ValueError as e:
            assert isinstance(e, ValueError)

        # TODO - Test the randomization of box parameters as well
