class StartupRefused(Exception):
    """
    The bot can't start: something it needs is missing or wired wrong. Says what,
    and what to do.

    One class for every startup refusal, whether the readers' sprites are missing
    (`maple/screen/sprites.py`) or a DecisionMaker declares something that resolves
    to nothing (`botting/core/supervisor.py`), so a caller catches one thing.
    """
