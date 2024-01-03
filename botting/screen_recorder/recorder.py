import cv2
import ctypes
import logging
import multiprocessing.connection
import os
import time

from botting.utilities import config_reader, ChildProcess, take_screenshot
from .folder_manager import FolderManager

SM_CXSCREEN = 0
SM_CYSCREEN = 1

logger = logging.getLogger(__name__)


class RecorderLauncher:
    """
    Launches a Recorder ChildProcess, which is responsible for recording the entire session.
    An independent multiprocessing.Process is created to handle the screen recording.
    Recording is CPU-intensive and should not be done in the same process as the Bot.
    """

    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.recorder_receiver, self.recorder_sender = multiprocessing.Pipe(
            duplex=False
        )  # One way communication
        self.logging_queue = queue
        self.recorder_process = None

    def __enter__(self) -> None:
        self.recorder_process = multiprocessing.Process(
            target=self.start_recording,
            name="Screen Recorder",
            args=(self.recorder_receiver, self.logging_queue),
        )
        self.recorder_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.recorder_sender.send(None)
        self.recorder_sender.close()
        logger.debug("Sent stop signal to recorder process")
        self.recorder_process.join()
        logger.info(f"RecorderLauncher exited.")

    @staticmethod
    def start_recording(
        receiver: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
    ):
        recorder = Recorder(log_queue, receiver)
        recorder.start()


class Recorder(ChildProcess):
    """
    Loads in relevant recording parameters (user-specified) and records the entire session.
    At the end of the session, the recording is saved.
    The recorder is expected to run in a child process (separated from main process).
    As such, it inherits from ChildProcess and relies on its connection with Main
     Process to know when to stop.
    """

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        end_pipe: multiprocessing.connection.Connection,
        config_name: str = "recordings",
    ) -> None:
        """
        :param end_pipe: End of the Pipe object that is connected to the main process.
        :param config_name: Name of the config file to use. Defaults to "recordings".
        """
        super().__init__(log_queue, end_pipe)
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

    def start(self) -> None:
        """
        Loops until it is told to stop and record images at regular intervals, based on user config.
        :return: None
        """
        try:
            logger.info(
                f"Screen recorder started. Saving recording to {os.path.normpath(os.path.join(self.out_path))}"
            )
            while True:
                beginning = time.perf_counter()

                img = take_screenshot()
                # gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                self.output.write(img)

                end = time.perf_counter()
                time.sleep(
                    max(1 / int(self.config["fps"]) - (end - beginning), 0)
                )  # Ensure that no more than user-specified FPS are recorded (prevents files from getting too large)
                if self.stop_recording():
                    logger.info(
                        f"Screen recorder stopped. Saving recording to {os.path.normpath(os.path.join(self.out_path))}"
                    )
                    self.output.release()
                    break
        except Exception as e:
            raise
        # Failsafe to ensure video is properly saved at the end of the recording session
        finally:
            if self.output.isOpened():
                logger.error(
                    f"Screen recorder has unexpectedly stopped. Saving recording to {os.path.normpath(os.path.join(self.out_path))}"
                )
                self.output.release()
            self.output_manager.perform_cleanup()

    def stop_recording(self) -> bool:
        if self.pipe_end.poll():
            if self.pipe_end.recv() is None:
                self.pipe_end.close()
                return True
        return False
