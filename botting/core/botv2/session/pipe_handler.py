import multiprocessing.connection


class PipeHandler:
    """
    Handles bidirectional communication through a Pipe object.
    """
    def __init__(self, pipe):
        self.pipe = pipe
        self.proc_name = multiprocessing.current_process().name
        self._validated = False

    def send(self, func: callable, *args, **kwargs):
        """
        Called from Child processes only.
        Objects that send data through a pipe (Ex; Engines) usually call a function
        and only send if the function returns a non-None value.
        :param func: The function to call.
        :param args: The arguments to pass to the function.
        :param kwargs: The keyword arguments to pass to the function.
        :return:
        """
        if not self._validated:
            self._validated = True
            assert self.proc_name != "MainProcess", (
                "PipeHandler.send() should only be called from a Child Process."
            )
        data = func(*args, **kwargs)
        if data is not None:
            self.pipe.send(data)

    def recv(self):
        """
        Called from Main Process only.
        Objects that receive data through a pipe (Ex; EngineListeners).

        :return:
        """
        if not self._validated:
            self._validated = True
            assert self.proc_name == "MainProcess", (
                "PipeHandler.recv() should only be called from the Main Process."
            )
        return self.pipe.recv()
