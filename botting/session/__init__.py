"""
The Session reader: one Session's ``telemetry.jsonl``, read deterministically.

``python -m botting.session summary|events|around [DIR]`` is how an agent
reads a Session, instead of parsing the file itself (``cli``). ``reading``
loads the records, keeps the clock and holds the filters. ``watch`` and
``stop`` follow a Session still running, and ``stop`` writes its stop file
(``live``).

It reads only the ADR 0001 envelope, so it is generic and lives in the engine:
nothing in it knows a game. ``session.started``, ``session.ended`` and
``action.finished`` are the only Event Types it gives a meaning to.
"""

from .cli import main
from .reading import Record, Session, SessionError, load_session

__all__ = ["Record", "Session", "SessionError", "load_session", "main"]
