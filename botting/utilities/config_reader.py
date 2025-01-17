import os
import logging
from configparser import ConfigParser, SectionProxy
from paths import ROOT

logger = logging.getLogger(__name__)


def config_reader(
    filename: str,
    section: str | None = None,
    option: str | None = None,
    file_ext: str = ".ini",
    *,
    full_path: str | None = None,
) -> ConfigParser | SectionProxy | str | None:
    """
    Function that reads a config file from the config directory (default).
    If a full path is provided, it will read the config file from that path instead.
    :param filename: filename of the config file to be read.
     Must exist in the config directory, otherwise a FileNotFoundError will be raised.
    :param section: section of the config file to be read.
     If None, all sections will be read. Must exist in config file.
    :param option: option of the config file to be read.
     If None, all options will be read. If section is None, this parameter is ignored.
      Must exist in config file.
    :param file_ext: file extension of the config file to be read. Default is '.ini'.
    :param full_path: If provided, the config is read from this full path instead.
    :return: ConfigParser object.
    """
    config = ConfigParser()
    if full_path is None:
        full_path = os.path.join(ROOT, "configs", filename + file_ext)
    assert os.path.exists(full_path), f"Config file {full_path} does not exist."
    config.read(full_path)

    logger.debug(f"config read successfully from {full_path}")
    if section is not None:
        if option is not None:
            return config[section][option]
        return config[section]
    return config
