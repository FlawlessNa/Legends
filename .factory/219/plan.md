---
ticket: 219
stage: build
radius:
  - factory/state.py
  - factory/cli.py
  - factory/AGENTS.md
  - tests/test_factory/test_state.py
  - tests/test_factory/test_park.py
  - tests/test_factory/test_cli.py
  - docs/factory/design.md
  - docs/factory/artifacts.md
  - .factory/219/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_state.py::test_two_processes_updating_at_once_lose_neither_update
  red_output_sha: b4ede29c4326
  suite: pass
docs_cleared: []
---

# Plan: the factory loop's state outside the worktrees, and factory park

## Radius

| Path | Why |
| --- | --- |
| `factory/state.py` | new: `TicketState`, `StateError`, `load`, `update`, `with_log`, `dispatched`, `render_run_md`, and the private `_save` |
| `factory/cli.py` | `park` registered in `COMMANDS`; its flags and handler. Reuses `_session_checkout` and `_ticket_root` |
| `factory/AGENTS.md` | one paragraph: where loop state lives, and that writers go through `update` |
| `tests/test_factory/test_state.py` | new: the state, its failures, the interrupted write, the lock, `render_run_md`, `git status` |
| `tests/test_factory/test_park.py` | new: `factory park`, on real temporary git repositories |
| `tests/test_factory/test_cli.py` | one changed test, see Deviations: a command with a required flag cannot parse bare |
| `docs/factory/design.md` | §9's `park` row lists the exit codes; the `park.md` row in the artifact table adds its fields |
| `docs/factory/artifacts.md` | `park.md` adds `ticket` and `parked_at`; `run.md` lists its fields |

`factory/chain.py`, `factory/routing.py` and `factory/worktrees.py` are used as
they are: `common_dir`, `resolve`, `worktree_for`, `read_chain(...).park`.
`factory/**` is protected, so this PR is a human merge.

## Order of work

1. Write the red tests; run them against the unchanged source; save the `E` lines.
2. `factory/state.py`, then `park` in `cli.py`.
3. `design.md`, `artifacts.md`, `AGENTS.md`.
4. Full suite, ruff, pyright.

## Design in brief

- **Path.** `<common_dir>/factory/<n>/state.json`, next to `state.lock`.
  `common_dir` is None outside a repository: `StateError`.
- **Stored fields**, exactly twelve. `accepted` is a nested record of four
  strings or null; `log` is a list of `{at, event, detail}`.
- **Write.** `state.json.tmp-<pid>` in the same directory, `flush`, `fsync`,
  then `os.replace`, with `PermissionError` retried 50 times 20 ms apart, then
  `StateError`. A leftover temp file is never read.
- **Read.** `load` takes no lock. `PermissionError` is retried the same way and
  is never "missing"; only `FileNotFoundError` gives the fresh state.
- **Lock.** `update` holds an exclusive lock on `state.lock`
  (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere) across read, change
  and write.
- **`park`** resolves the ticket as `_next` does, asks `routing.resolve` for the
  stage (null when it gives none or raises), and creates `park.md` with
  exclusive-create, so a second park is exit 3 even in a race.

## The four notes from the passing spec review (cycle 2), settled

a. **`_save` is private.** There is no public direct write. Every writer calls
   `update(repo_root, ticket, change)`, which creates the state on first use, so
   #222 cannot bypass the lock. The module docstring says so. Tests that need
   the write path alone go through `update` with the monkeypatched `os.replace`.
b. **The concurrent test fails every time without the lock.** Two processes
   wait until a common start time, then each `update`s with a change function
   that reads `attempt`, sleeps 0.3 s, and returns `attempt + 1`. Unlocked, both
   read 0 and the file ends at 1; locked it ends at 2. I will also disable the
   lock by hand and run it, to see it red. The lock wait is bounded (10 s), then
   `StateError`, on both `msvcrt` and `fcntl`; a test holds the lock in another
   process and sees the error with a short timeout.
c. **`park.md` into `state.parked`** is #159's `snapshot()`. `park` here never
   writes `state.json`; `parked` is a stored string, null by default.
d. **`dispatched(state, stage) -> TicketState`** is pure: the first dispatch of
   a stage is attempt 1, the second 2, and a new stage resets to 1. Tested.

Also: malformed JSON and a bad version name the file only, as there is no field
to name; every other error names the file and the field.

## Decisions I made

- `update` refuses a change that is not an append to the log, or that renames
  the ticket, with `StateError`: "the log only ever grows" is enforced where
  every writer passes.
- `render_run_md` writes `cycles` as a nested block (`cycles:` then indented
  `<stage>: n`), which `chain.front_matter` reads as `cycles.<stage>`.
- A whitespace-only `--reason` or `--question` is empty text (exit 2).
- `park` resolves with `routing.resolve`; any `ValueError` (including
  `MalformedVerdict` and `UnknownChainVersion`) gives `stage: null`.

## For the PR body

- Protected path (`factory/**`): a human merges.
- Nothing here changes which keys reach the game.

## Named changed test

| Test | Behaviour that moved |
| --- | --- |
| `test_cli.py::test_every_registered_command_is_reachable_through_the_parser` | it parsed every command bare; `park` has a required flag group by spec, so it now passes `--reason x` for `park` only. Every command is still parsed and its name checked |

## Proof

**Red, before the change.** `test_park.py` and `test_state.py` were run against the unchanged source (`--continue-on-collection-errors`); the `E` lines are in the scratchpad file `red219.txt` (sha256 prefix `b4ede29c4326`).

- `test_state.py` (42 tests) fails to collect: `ImportError: cannot import name 'state' from 'factory'`. Every state test is red for the same reason, so that line proves only that the module did not exist. The behaviour tests below were checked by hand instead.
- `test_park.py`: 23 failed. 18 `argparse.ArgumentError: ... invalid choice: 'park'` (exit 2 from `SystemExit`); the three flag-misuse tests also fail on their message check (`required`, `not allowed with`, `expected one argument`), so they do not pass merely because an unknown command exits 2; `design.md`'s park row lists no "already exists" code; `artifacts.md`'s `park.md` has no `ticket`.

**By hand, the lock.** With the `msvcrt.locking` call in `_try_lock` replaced by `return`, `test_two_processes_updating_at_once_lose_neither_update` failed 3 runs out of 3 with `assert 1 == 2`; restored, it passes. The interrupted-write test asserts what the fake `os.replace` is given (exists, same directory, new content) before raising.

**Green, after.** `pytest` from the worktree root: `1571 passed, 3 skipped, 25 deselected`, 0 failed, 0 errors, 0 xfailed. `ruff check`, `ruff format` and `pyright` are clean on the changed Python files; pre-commit passed on the change commit.

## Could not verify

- **The killed process was simulated by raising.** The interrupted-write test makes `os.replace` raise a `BaseException` after the temporary file is written; no process was killed with `taskkill` or `SIGKILL`, and no power loss was tried. That the OS releases `state.lock` when its holder dies is the documented behaviour of `msvcrt.locking` and `flock`, not something measured here (the test shows only that a raised exception releases it).
- **The `fcntl` branch** did not run: this machine is Windows. It is written and not exercised, so the bounded wait on POSIX is untested.
- **fsync reaching disk.** It is called; whether the device honours it is the OS's.
- **The red tests were committed with the change**, not before it: `test_state.py` imports `factory.state`, which pre-commit's pyright refuses before it exists.
- **`park` from a judge's snapshot, the Designer's branch name, and routing reading `park.md`** are out of scope (#159, #222, #218).
- **No live `factory park` by a real worker** was run; the tests call `main` with the session's directory set by `chdir`.
