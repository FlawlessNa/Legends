import logging

import pytest

from botting.utilities.config_reader import logger, config_reader


def test_config_reader(caplog):
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        config_reader(filename="game", section="Client", option="Window Titles")
    assert caplog.records

    with pytest.raises(AssertionError):
        config_reader(filename="keybindings", file_ext=".txt")

    with pytest.raises(KeyError):
        config_reader(filename="keybindings", section="random_section")

    with pytest.raises(KeyError):
        config_reader(filename="game", section="Client", option="random_option")
