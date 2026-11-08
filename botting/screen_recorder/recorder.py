import asyncio
import ctypes
import logging
import os
import time
from configparser import ConfigParser

import cv2

from botting.telemetry import emit_event
from botting.telemetry_events import (
    RECORDING_CHECKPOINT,
    RECORDING_STARTED,
    RecordingCheckpointPayload,
    RecordingStartedPayload,
)
from botting.utilities import config_reader, take_screenshot

from .folder_manager import FolderManager

SM_CXSCREEN = 0
SM_CYSCREEN = 1

logger = logging.getLogger(__name__)

DEFAULT_SECTION = "DEFAULT"


def section_config(parser: ConfigParser, section: str) -> dict[str, str]:
    """
    One section's options, falling back to ``DEFAULT`` for any it leaves out
    (``ConfigParser`` does that itself). A section the file lacks is tolerated:
    the result is ``DEFAULT`` alone, with a warning.
    :param parser: The parsed ``recordings.ini``.
    :param section: The section to read, such as ``"TEST"``.
    """
    if section != DEFAULT_SECTION and not parser.has_section(section):
        logger.warning(
            "recordings.ini has no [%s] section; using [%s].", section, DEFAULT_SECTION
        )
        section = DEFAULT_SECTION
    return dict(parser[section])


class Recorder:
    """
    Loads in relevant recording parameters (user-specified) and records the entire
    session. At the end of the session, the recording is saved.
    The recorder is expected to run in a child process (separated from main process).
    """

    def __init__(
        self,
        config_name: str = "recordings",
        section: str = DEFAULT_SECTION,
    ) -> None:
        """
        :param config_name: Name of the config file to use. Defaults to "recordings".
        :param section: The section to read, over ``DEFAULT``. A test Session passes
        ``"TEST"``. A section the file lacks falls back to ``DEFAULT``.
        """
        parser = config_reader(config_name)
        assert isinstance(parser, ConfigParser)
        self.config: dict = section_config(parser, section)
        self.out_path: str = str(
            os.path.join(
                self.config["recordings folder"],
                time.strftime("%Y%m%d_%H%M%S") + self.config["file extension"],
            )
        )
        self.output: cv2.VideoWriter = cv2.VideoWriter(
            self.out_path,
            cv2.VideoWriter.fourcc(*self.config["four cc"]),
            int(self.config["fps"]) * float(self.config["multiplier"]),
            (
                ctypes.windll.user32.GetSystemMetrics(SM_CXSCREEN),
                ctypes.windll.user32.GetSystemMetrics(SM_CYSCREEN),
            ),
        )
        self.output_manager: FolderManager = FolderManager(
            folder_path=self.config["recordings folder"],
            max_folder_size=int(self.config["max recordings folder size (gb)"]),
        )

    async def start(self) -> None:
        """
        Loops until it is told to stop and record images at regular intervals,
        based on user config.
        :return: None
        """
        try:
            logger.info(
                "Screen recorder started. Saving recording to %s",
                os.path.normpath(os.path.join(self.out_path)),
            )
            started: RecordingStartedPayload = {
                "path": self.out_path,
                "fps": int(self.config["fps"]) * float(self.config["multiplier"]),
            }
            emit_event(None, RECORDING_STARTED, started, logger_name=logger.name)
            checkpoint_every = int(self.config["fps"])
            frame_index = 0
            while True:
                beginning = time.perf_counter()
                img = take_screenshot()
                self.output.write(img)
                if frame_index % checkpoint_every == 0:
                    checkpoint: RecordingCheckpointPayload = {
                        "frame_index": frame_index
                    }
                    emit_event(
                        None, RECORDING_CHECKPOINT, checkpoint, logger_name=logger.name
                    )
                frame_index += 1
                end = time.perf_counter()

                await asyncio.sleep(
                    max(1 / int(self.config["fps"]) - (end - beginning), 0)
                )  # Ensure that no more than user-specified FPS are recorded

        except asyncio.CancelledError:
            logger.info(
                "Screen recorder stopped. Saving recording to %s",
                os.path.normpath(os.path.join(self.out_path)),
            )

        except Exception:
            logger.error(
                "Screen recorder has unexpectedly stopped. Saving recording to %s",
                os.path.normpath(os.path.join(self.out_path)),
            )
            raise
        finally:
            # Ensure video is properly saved at the end of the recording session
            self.output.release()
            self.output_manager.perform_cleanup()
