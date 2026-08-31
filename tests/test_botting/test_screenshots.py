"""
The most important thing here is to test that take_screenshot works under multiprocess,
multi-threaded, and asynchronous framework.
"""

import pytest

#: Both tests below are unwritten placeholders whose body is `pytest.fail()`.
#: See the note in `test_controller.py` and issue #89.
pytestmark = pytest.mark.xfail(
    reason="Unwritten placeholder; see issue #89", strict=True
)


def test_take_screenshot() -> None:
    pytest.fail()


def test_find_image() -> None:
    pytest.fail()
