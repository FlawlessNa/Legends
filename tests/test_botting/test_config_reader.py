import logging

import pytest

from botting.utilities.config_reader import config_reader, logger

#: A committed config, so the cases below that need a file to *exist* do not
#: depend on whichever personal configs a checkout happens to carry.
#: `configs/keybindings.ini` is gitignored and ships only as
#: `keybindings.example.ini`, so pointing any of these at it made the module
#: fail on a clean checkout (#115).
TRACKED_CONFIG = "game"


def test_config_reader(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        config_reader(filename=TRACKED_CONFIG, section="Client", option="Class Name")
    assert caplog.records

    with pytest.raises(AssertionError):
        config_reader(filename=TRACKED_CONFIG, file_ext=".txt")

    with pytest.raises(KeyError):
        config_reader(filename=TRACKED_CONFIG, section="random_section")

    with pytest.raises(KeyError):
        config_reader(filename=TRACKED_CONFIG, section="Client", option="random_option")
