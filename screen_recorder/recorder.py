import cv2
import ctypes
import os
import time

from screen_recorder.folder_manager import FolderManager
from utilities import config_reader, take_screenshot

SM_CXSCREEN = 0
SM_CYSCREEN = 1


class Recorder:
    """
    Loads in relevant recording parameters (user-specified) and records the entire session.
    At the end of the session, the recording is saved.
    A callable needs to be provided when instantiating this class. This callable will be used to check when the recording should stop.
    """

    def __init__(self, func: callable, config_name: str = "recordings") -> None:
        self.config: dict = dict(config_reader(config_name)["DEFAULT"])
        self.out_path = os.path.join(
            self.config["recordings folder"],
            time.ctime().replace(":", "_") + self.config["file extension"],
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
        self.stop_recording = func

    def start_recording(self) -> None:
        """
        Loops until it is told to stop and record images at regular intervals, based on user config.
        :return: None
        """
        try:
            while True:
                beginning = time.perf_counter()

                img = take_screenshot()
                self.output.write(img)

                end = time.perf_counter()
                time.sleep(max(1 / int(self.config["fps"]) - (end - beginning), 0))  # Ensure that no more then user-specified FPS are recorded (prevents files from getting too large)

                if self.stop_recording():
                    # logger.info(f'Screen recorder has stopped. Saving recording to {os.path.normpath(os.path.join(self.output_path, self.output_name))}')
                    self.output.release()
                    break

        # Failsafe to ensure video is properly saved at the end of the recording session
        finally:
            if self.output.isOpened():
                # logger.info(f'Screen recorder has *unexpectedly* stopped. Saving recording to {os.path.normpath(os.path.join(self.output_path, self.output_name))}')
                print("saving video")
                self.output.release()
                print("video saved")
            self.output_manager.perform_cleanup()
