class StartupRefused(Exception):
    """
    The bot can't start: something it needs is missing or wired wrong. Says what,
    and what to do.

    One class for every startup refusal, whether the readers' sprites are missing
    (`maple/screen/sprites.py`) or a DecisionMaker declares something that resolves
    to nothing (`botting/core/supervisor.py`), so a caller catches one thing.
    """


class DecisionMakerCrashed(Exception):
    """
    A DecisionMaker's decision loop raised. The loop raises this, chaining the
    exception it caught, so the Bot's `ExceptionGroup` names the DecisionMaker
    that ended the Bot and the Engine can report it.
    """

    def __init__(self, decision_maker: str, error: BaseException) -> None:
        """
        :param decision_maker: The crashed DecisionMaker, as its `repr` names it.
        :param error: What its loop raised.
        """
        super().__init__(f"{decision_maker} crashed: {type(error).__name__}: {error}")
        self.decision_maker = decision_maker
