"""
Entry point, so the factory runs as `python -m factory <command>`.

The repo has no `[project]` table and ships no console scripts -- `maple` is run
the same way (`python -m maple.launchers.run`), so this follows the convention
already in the tree rather than introducing packaging metadata. See
`factory/AGENTS.md`.
"""

from __future__ import annotations

import sys

from factory.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
