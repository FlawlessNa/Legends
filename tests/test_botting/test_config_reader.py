from botting.utilities.config_reader import logger, config_reader

from unittest import TestCase


class Test(TestCase):
    def setUp(self) -> None:
        self.logger = logger

    def test_config_reader(self):
        with self.assertLogs(self.logger, level="DEBUG") as cm:
            config_reader(filename="game", section="Client", option="Window Titles")

        with self.assertRaises(AssertionError):
            config_reader(filename="keybindings", file_ext=".txt")

        with self.assertRaises(KeyError):
            config_reader(filename="keybindings", section="random_section")

        with self.assertRaises(KeyError):
            config_reader(filename="game", section="Client", option="random_option")
