import asyncio
import cv2
import ctypes
import logging
import os
import time

from botting.utilities import config_reader, take_screenshot
from .folder_manager import FolderManager

SM_CXSCREEN = 0
SM_CYSCREEN = 1

logger = logging.getLogger(__name__)


class Recorder:
    """
    Loads in relevant recording parameters (user-specified) and records the entire
    session. At the end of the session, the recording is saved.
    The recorder is expected to run in a child process (separated from main process).
    """

    def __init__(
        self,
        config_name: str = "recordings",
    ) -> None:
        """
        :param config_name: Name of the config file to use. Defaults to "recordings".
        """
        self.config: dict = dict(config_reader(config_name)["DEFAULT"])
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
                f"Screen recorder started. Saving recording to "
                f"{os.path.normpath(os.path.join(self.out_path))}"
            )
            while True:
                beginning = time.perf_counter()
                img = take_screenshot()
                self.output.write(img)
                end = time.perf_counter()

                await asyncio.sleep(
                    max(1 / int(self.config["fps"]) - (end - beginning), 0)
                )  # Ensure that no more than user-specified FPS are recorded

        except asyncio.CancelledError:
            logger.info(
                f"Screen recorder stopped. Saving recording to "
                f"{os.path.normpath(os.path.join(self.out_path))}"
            )

        except Exception as e:
            logger.error(
                f"Screen recorder has unexpectedly stopped. Saving recording to "
                f"{os.path.normpath(os.path.join(self.out_path))}"
            )
            raise
        finally:
            # Ensure video is properly saved at the end of the recording session
            self.output.release()
            self.output_manager.perform_cleanup()
