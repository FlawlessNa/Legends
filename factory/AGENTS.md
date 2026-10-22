# factory — agent instructions

<!-- Read directly by Claude Code; there is no CLAUDE.md shim (#191). -->

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
factory <command> [--json]
python -m factory <command> [--json]
```

Both work and both reach the same `main`. CI calls the console script. The
hooks do not: the console script exists only on an activated venv's `PATH`, and
the hook shell has none (#199). So `.claude/hooks/factory-hook.sh` finds the
venv interpreter by path and runs `python -I -m factory hook <event>`. See
"Which code a hook runs" below.

It is installed editable, once, into the project venv:

```
pip install -e . --no-deps
```

`--no-deps` is deliberate. `pyproject.toml` declares `dependencies = []` and
packages `factory` alone: `requirements.txt` still owns the bot's dependency
set, and pinning is a maintainer decision (`AGENTS.md`). Packaging the factory
must never become a second, competing place where the project's dependencies
are declared.

`botting` and `maple` are not packaged and keep running as they always have
(`python -m maple.launchers.run`).

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

## The hooks, and how to turn them off

`factory hook <event>` answers three Claude Code events, registered in the
tracked `.claude/settings.json`. They are the **floor**: project settings hooks
bind every session in the repo, including a human's. SDK per-role hooks (#163)
are a separate, narrower layer.

| Event | Refuses |
| --- | --- |
| `session-start` | Nothing. Reports the chain state so nobody can say they did not know |
| `pre-tool-use` | A write outside `.factory/` while `spec.md` or `spec-review.md` is missing |
| `stop` | Finishing when source changed and `plan.md` records no proof |

All three are inert off an `issue/<n>-*` branch, and writes to `.factory/`
itself are always allowed — refusing those would forbid the only action that
could satisfy the gate.

**The override**, because a gate nobody can bypass in an emergency is a gate
someone eventually deletes instead. In `.claude/settings.local.json`, which is
gitignored and personal:

```json
{ "env": { "FACTORY_HOOKS": "off" } }
```

Using it is not cheating; not saying you used it is. The PR body is where that
goes.

**Which code a hook runs.** The hook runs the factory installed in the venv:
the editable install, which points at the **main checkout's** `factory/`. It
never runs a worktree's own copy, whatever directory the session sits in.
`-I` (isolated mode) is what guarantees this. Plain `python -m` puts the
current directory first on the import path, and the hook runs in the session's
directory, so a worktree editing `factory/` was judged by its own unfinished
gates (#216). Two consequences:

- The gates are whatever the main checkout has checked out. Keep it current.
- Bash-run hook tests in a ticket worktree exercise the main checkout's
  `factory/`, not the branch's. The in-process tests (`main([...])`) test the
  branch.

The session's directory is taken from the event's `cwd` when it names one, and
from the process cwd otherwise.

**They enforce the sequence, not the quality.** That `spec-review.md` exists is
a `stat`. That the review was any good needs #180. A green hook is not a
reviewed spec, and `factory hook` is the one subcommand that does not obey the
exit-code contract — it speaks the harness's JSON protocol and always exits 0,
because a hook that fails must not take the session down with it.

## The merge policy

`factory merge check <pr>` evaluates `docs/factory/merge-policy.md` for one PR,
exactly as the workflow does, and never merges. Exit 0 means CI would merge it;
1 means its author can fix what failed; 3 means a person merges it.

`factory/merge.py` keeps three layers apart: `evaluate` is pure, `gather` reads
GitHub through an injected `gh` runner, `check` joins them. Put a new condition
in `evaluate` and nowhere else — not in the workflow, not in the dispatcher.

**Every module the console script imports is protected**: a PR touching one
never auto-merges, because it could change the verdict on itself. A test
computes that closure, so adding an import to `cli.py` or anything it reaches
fails the suite until the module is added to `POLICY.protected_paths` — and that
edit, being to `merge.py`, waits for a person too. That is the intent.

## Gates

Same as the rest of the tree: `pytest` green, `ruff check` and `ruff format`
clean, Pyright at `standard` (this package is in the `include` list). Tests live
in `tests/test_factory/`.
