"""
The engine's core: Bots, DecisionMakers, their Supervisor, Data Keys and Signals,
the game window's handle, and the processes a Session runs.

Members load lazily (PEP 562): `from botting.core import Bot` imports `bot.py`
when it is asked for, not before. Importing one light submodule, such as
`botting.core.errors` for `StartupRefused`, runs this file, and an eager import
of every member would load `bot.py` and `session_manager.py`, and through them
the input modules (`botting.controller`). A tool that must send no input
(`toolkit/position_check.py`) imports `StartupRefused` through
`maple.screen.sprites`, so it would load them.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .action_data import ActionRequest, ActionWithValidation, DiscordRequest
    from .async_task_manager import AsyncTaskManager
    from .bot import Bot
    from .bot_data import BotData, OwnedByProvider
    from .data_keys import Key, KeyNotDeclared, Provider, Providers
    from .decision_maker import (
        DecisionLoop,
        DecisionMaker,
        PauseNotDeclared,
        action_name,
    )
    from .engine import Engine
    from .errors import StartupRefused
    from .metadata import MetadataNamespace
    from .peripherals_process import PeripheralsProcess
    from .proxy_factory import ProxyFactory
    from .session_manager import SessionManager
    from .signals import Announcement, Signal, SignalBoard, SignalNotDeclared
    from .supervisor import Pause, PauseTarget, Supervisor
    from .window import HANDLE, WindowProvider

__all__ = [
    "HANDLE",
    "ActionRequest",
    "ActionWithValidation",
    "Announcement",
    "AsyncTaskManager",
    "Bot",
    "BotData",
    "DecisionLoop",
    "DecisionMaker",
    "DiscordRequest",
    "Engine",
    "Key",
    "KeyNotDeclared",
    "MetadataNamespace",
    "OwnedByProvider",
    "Pause",
    "PauseNotDeclared",
    "PauseTarget",
    "PeripheralsProcess",
    "Provider",
    "Providers",
    "ProxyFactory",
    "SessionManager",
    "Signal",
    "SignalBoard",
    "SignalNotDeclared",
    "StartupRefused",
    "Supervisor",
    "WindowProvider",
    "action_name",
]

#: Each public name, and the submodule that defines it.
_MEMBERS: dict[str, str] = {
    "ActionRequest": "action_data",
    "ActionWithValidation": "action_data",
    "DiscordRequest": "action_data",
    "AsyncTaskManager": "async_task_manager",
    "Bot": "bot",
    "BotData": "bot_data",
    "OwnedByProvider": "bot_data",
    "Key": "data_keys",
    "KeyNotDeclared": "data_keys",
    "Provider": "data_keys",
    "Providers": "data_keys",
    "DecisionLoop": "decision_maker",
    "DecisionMaker": "decision_maker",
    "PauseNotDeclared": "decision_maker",
    "action_name": "decision_maker",
    "Engine": "engine",
    "StartupRefused": "errors",
    "MetadataNamespace": "metadata",
    "PeripheralsProcess": "peripherals_process",
    "ProxyFactory": "proxy_factory",
    "SessionManager": "session_manager",
    "Announcement": "signals",
    "Signal": "signals",
    "SignalBoard": "signals",
    "SignalNotDeclared": "signals",
    "Pause": "supervisor",
    "PauseTarget": "supervisor",
    "Supervisor": "supervisor",
    "HANDLE": "window",
    "WindowProvider": "window",
}


def __getattr__(name: str) -> Any:  # noqa: ANN401 - whichever member is asked for
    """Import the submodule that defines `name`, once, and keep the member."""
    submodule = _MEMBERS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    member = getattr(import_module(f".{submodule}", __name__), name)
    globals()[name] = member
    return member


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
