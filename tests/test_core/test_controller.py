from unittest import TestCase

"""Idea: Create a multiprocess. One will receive input through the builtin input() function, the other one sends the desired input. Then, assess that the received input is the same."""
"""
Another idea: into the actual inputs/controller classes, for the exported DLL functions, add an .errcheck attribute with a callable. The callable is used to validate the return type of the function.
This could be handy for testing purposes.
"""

class TestController(TestCase):
    def test_activate(self):
        self.fail()

    def test_key_binds(self):
        self.fail()

    def test_hold_key(self):
        self.fail()

    def test_press(self):
        self.fail()

    def test__non_silent_press(self):
        self.fail()
