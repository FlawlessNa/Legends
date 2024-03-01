from .monitor import Monitor


class Engine:
    """
    Lives in a ChildProcess.
    An engine instance is a container of Monitor instances.
    It cycles through each Monitor instance, calling their DecisionMakers one at a time.
    It is responsible for passing on the ActionData instances returned by the
    DecisionMakers to the Main Process, as well as receiving (from Main Process)
    residual MonitorData attributes to update.
    """
    def __init__(self, monitors: list[Monitor]) -> None:
        self.monitors = monitors

    def _exit(self) -> None:
        """
        This method is called when the Engine is about to be terminated.
        Performs any necessary clean-up.
        1. Ensures not keys are being held down on any of the monitors.
        2.
        :return:
        """
        for monitor in self.monitors:
            for key in ["up", "down", "left", "right"]:
                asyncio.run(
                    controller.press(
                        bot.handle, key, silenced=False, down_or_up="keyup"
                    )
                )

