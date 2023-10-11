from unittest import TestCase
from utilities import randomize_params, Box


class Test(TestCase):
    def test_randomize_params(self):
        defaults = [
            self._test_function1(),
            self._test_function2(),
            self._test_function3(),
            self._test_function4(),
        ]

        for i in range(1000):
            # Testing that defaults are randomized if no parameters are specified for both randomize_args and the underlying function
            res = [
                randomize_params()(self._test_function1)(),
                randomize_params()(self._test_function2)(),
                randomize_params()(self._test_function3)(),
                randomize_params()(self._test_function4)(),
            ]
            self._standard_comparison(res, defaults)

            # Testing that assert is raised when arguments specified into randomize_args are not specified in the underlying function
            with self.assertRaises(AssertionError):
                randomize_params("d")(self._test_function1)("a", 10, 15.2)
            with self.assertRaises(AssertionError):
                randomize_params("d")(self._test_function2)("a", 10, 15.2)
            with self.assertRaises(AssertionError):
                randomize_params("d")(self._test_function3)("a", 10, 15.2)
            with self.assertRaises(AssertionError):
                randomize_params("d")(self._test_function4)("a", 10, 15.2)

            # Testing that only specified params are randomized, and within expected range. Other params are left untouched.
            res = [
                randomize_params("c", "kw_c")(self._test_function1)(b=10, kw_b=10),
                randomize_params("c", "kw_c")(self._test_function2)(
                    "5", 10, kw_b=10, kw_c=15.0
                ),
                randomize_params("kw_c")(self._test_function3)(kw_c=15.0),
                randomize_params("kw_a")(self._test_function4)(c=15.0),
            ]
            keys = [("c", "kw_c"), ("c", "kw_c"), ("kw_c",), ("kw_a",)]
            self._standard_comparison(res, defaults, randomized_keys=keys)

            # Testing that ignore_args works properly
            res = [
                randomize_params(ignore_args=["b", "c"])(self._test_function1)(
                    a="5", b=10, kw_b=10
                ),
                randomize_params("c", ignore_args="kw_c")(self._test_function2)(
                    "5", 10, kw_b=10, kw_c=15.0
                ),
                randomize_params("kw_c", ignore_args="kw_c")(self._test_function3)(
                    "5", 10, kw_c=15.0
                ),
                randomize_params("b", "c", "kw_b", ignore_args="kw_c")(
                    self._test_function4
                )(c=15.0),
            ]
            keys = [("a", "kw_a", "kw_b", "kw_c"), ("c",), tuple(), ("b", "c", "kw_b")]
            self._standard_comparison(res, defaults, randomized_keys=keys)

            # Testing that convert_args works properly
            with self.assertRaises(AssertionError):
                randomize_params(convert_args={"kw_a": "int"})(self._test_function1)(
                    kw_a="5", kw_b=10, kw_c=15.0
                )

            # Nothing should happen when convert_args is specified but the requested args to randomize are not (int, float, Box)
            self.assertEqual(
                randomize_params("kw_a", convert_args={"kw_a": "int"})(
                    self._test_function1
                )(kw_a="5", kw_b=10, kw_c=15.0),
                self._test_function1(),
            )
            self.assertIsInstance(
                randomize_params("kw_a", convert_args={"kw_a": "int"})(
                    self._test_function1
                )(kw_a="5", kw_b=10, kw_c=15.0)["kw_a"],
                str,
            )

            self.assertIsInstance(
                randomize_params("kw_b", convert_args={"kw_b": "int"})(
                    self._test_function1
                )(kw_a="5", kw_b=10, kw_c=15.0)["kw_b"],
                int,
            )
            self.assertIsInstance(
                randomize_params("kw_b", convert_args={"kw_b": "float"})(
                    self._test_function1
                )(kw_a="5", kw_b=10, kw_c=15.0)["kw_b"],
                float,
            )
            self.assertIsInstance(
                randomize_params(convert_args={"kw_c": "int"})(self._test_function1)(
                    kw_a="5", kw_b=10, kw_c=15.0
                )["kw_c"],
                int,
            )
            self.assertIsInstance(
                randomize_params(convert_args={"kw_c": "float"})(self._test_function1)(
                    kw_a="5", kw_b=10, kw_c=15.0
                )["kw_b"],
                float,
            )

            # Testing that enforce_sign works properly
            self.assertTrue(
                -115
                <= randomize_params(abs_threshold=100, enforce_sign=False)(
                    self._test_function1
                )(kw_a="5", kw_b=10, kw_c=-15.0)["kw_c"]
                <= 85
            )
            try:
                self.assertTrue(
                    -115
                    <= randomize_params(abs_threshold=100, enforce_sign=True)(
                        self._test_function1
                    )(kw_a="5", kw_b=10, kw_c=-15.0)["kw_c"]
                    <= 85
                )
            except ValueError as e:
                self.assertIsInstance(e, ValueError)

            # TODO - Test the randomization of box parameters as well

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
        self,
        actuals,
        randomized,
        *,
        perc_threshold: float = 0.05,
        randomized_keys: list[tuple] | None = None,
    ) -> None:
        if randomized_keys is None:
            randomized_keys = [tuple(actual.keys()) for actual in actuals]
        for act, rand, rand_keys in zip(actuals, randomized, randomized_keys):
            self.assertTrue(act.keys() == rand.keys())
            for key in act.keys():
                if isinstance(act[key], (int, float)) and key in rand_keys:
                    self.assertTrue(
                        rand[key] * (1 - perc_threshold)
                        <= act[key]
                        <= rand[key] * (1 + perc_threshold)
                    )
                elif isinstance(act[key], Box) and key in rand_keys:
                    self.assertTrue(rand[key] in act[key])
                else:
                    self.assertEqual(act[key], rand[key])
