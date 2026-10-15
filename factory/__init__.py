"""
The software factory: the commands that drive a ticket from intent to merge.

A third top-level package beside `botting/` and `maple/`, held to the same gates
as the rest of the tree. It knows nothing about MapleStory and nothing about the
engine; it reads and writes the artifact chain under `.factory/<ticket>/`, and
shells out to git, pytest and `gh`.

See `factory/AGENTS.md` for the rules that apply inside this package.
"""

from __future__ import annotations

from factory.exit_codes import ExitCode

__all__ = ["ExitCode", "__version__"]

#: The factory's own version, independent of the bot's.
__version__ = "0.1.0"
