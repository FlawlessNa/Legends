import asyncio


class TaskWrapper(asyncio.Task):
    """
    Wrapper class for asyncio.Task.
    Adds a few convenience methods and attributes for managing tasks.
    """

    @classmethod
    def create_task(cls, coro, *args, **kwargs):
        """
        Create a new task from a coroutine.
        """
        return cls(coro, *args, **kwargs)
