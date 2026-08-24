"""
Idea: Create a multiprocess. One will receive input through the builtin input()
function, the other one sends the desired input. Then, assess that the received input is
the same.

Another idea: into the actual inputs/controller classes, for the exported DLL functions,
add an .errcheck attribute with a callable. The callable is used to validate the return
type of the function. This could be handy for testing purposes.

Idea - Use mock objects to properly test how the SendInput/PostMessage are called, (how
many times, with what arguments, etc).
"""

import pytest


def test_key_binds():
    pytest.fail()


def test_press():
    pytest.fail()


def test_write():
    pytest.fail()


def test_move():
    pytest.fail()


def test_mouse_move():
    pytest.fail()


def test_click():
    pytest.fail()
