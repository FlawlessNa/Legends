# factory — agent instructions

The software factory: the commands that drive a ticket from intent to merge.
A third top-level package beside `botting/` and `maple/`, held to the same gates
as the rest of the tree.

## What belongs here

Everything that reads or writes the artifact chain under `.factory/<ticket>/`,
computes which stage a ticket is in, or enforces a gate. Nothing that knows what
MapleStory is, and nothing that touches a game client.

**Dependency direction.** `factory` imports neither `botting` nor `maple`. It
reads their artifacts (`telemetry.jsonl`, `trial_records/`) as files and shells
out to `git`, `pytest` and `gh`. A reader for an engine format lives behind a
parser in this package, not behind an import of the engine — so a change to the
engine's internals cannot break the factory, and the factory can read a Session
recorded by a different revision of the bot than the one checked out.

This is not `toolkit/`. That directory is standalone scripts nothing imports,
exempt from the annotation rules. This package is production code: fully typed,
no `print`, tested.

## How it runs

```
python -m factory <command> [--json]
```

There is no console script. The repo ships no `[project]` table and runs its
other entry points the same way (`python -m maple.launchers.run`), so this
follows the convention already in the tree instead of introducing packaging
metadata. If a bare `factory` command is wanted later, that is a packaging
decision to take deliberately — it means declaring dependencies and a build
backend, and dependency pinning is on the `AGENTS.md` hard-stop list.

## The exit-code contract

Every command returns one of these and nothing else (`factory/exit_codes.py`):

| Code | Meaning | What the caller does |
| --- | --- | --- |
| 0 | The gate passed | Continue to the next stage |
| 1 | The gate failed | Fix it and re-run. Never proceed |
| 2 | Misuse — wrong arguments, or the wrong stage | Re-read `factory next` |
| 3 | Needs a human | Stop, comment on the ticket, hand back |

Code 3 is the point of the contract: it turns "stop and ask rather than
finishing" from a judgment an agent makes into a value it reads. Never return 1
for something a person has to settle, and never return 0 for something you did
not actually verify.

`MISUSE` is 2 because that is what `argparse` already exits with, so a bad
invocation lands in the right bucket without being wrapped.

## Adding a command

Register it in `COMMANDS` in `factory/cli.py`: a name, help text, a flag
configurator, and a handler. Nothing else in that module changes.

A handler **returns** `(ExitCode, payload)`. It never prints and never calls
`sys.exit` — the dispatcher owns both, so every command speaks JSON and prose
from one implementation and an agent never parses prose. `__main__.py` holds the
only `sys.exit` in the package.

`print` is unavailable: ruff's `T20` applies here. Write to `sys.stdout`
explicitly, so a stray debugging `print` cannot masquerade as contracted output.

## Gates

Same as the rest of the tree: `pytest` green, `ruff check` and `ruff format`
clean, Pyright at `standard` (this package is in the `include` list). Tests live
in `tests/test_factory/`.
