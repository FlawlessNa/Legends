---
ticket: 216
stage: design
method: suite
criteria:
  - run the way factory-hook.sh runs it, from a directory holding a factory package that would answer differently, the session-start hook prints the real heartbeat "factory gates: LIVE" and never the shadow's sentinel
  - the hook resolves factory through the interpreter's installed packages, with the current directory kept off the import path
  - every hook event takes its session root from the event's cwd field when that names an existing directory, and falls back to the process cwd when the field is absent or names no directory, with a test for pre-tool-use, a test for stop, and a test for a cwd that does not exist
  - when stdin is a terminal the hook reads nothing from it, so running factory-hook.sh by hand in a terminal does not hang
  - a pre-tool-use event whose cwd is a linked ticket worktree is judged with that worktree as the session, even when the process runs in an unrelated directory
  - a hook that cannot find an interpreter still prints its unreachable message and exits 0, unchanged from #199, tested by running a copy of the script from a directory with no venv
  - every existing test in tests/test_factory passes unmodified
  - factory/AGENTS.md says which code a hook runs and why the current directory is kept off the import path, and its sentence that hooks call the console script is corrected, since they run the interpreter by path
specified_by: claude
specified_at: 2026-10-22
revised_after: spec-review.md (changes-requested, 7 findings)
---

# Spec: the hook runs the main checkout's gate code

## Source

Issue #216, and `docs/factory/design.md` §3 (d4), §7 (last row) and §10.

## What changes

1. **`factory-hook.sh`** execs `"$python" -I -m factory hook "$event"`.
   - `-I` is isolated mode. On Python 3.14 it implies `-E -P -s`: environment variables like `PYTHONPATH` are ignored, the current directory is not prepended to `sys.path`, and the user site is skipped.
   - `factory` then resolves only through the venv's installed packages. Today that is the editable install in the primary checkout's `.venv`, which points at the primary checkout's `factory/`.
   - The script's comment says why, so nobody removes `-I` as noise.
2. **`_run_hook`** reads the event once, for every event. `session-start` and `stop` read nothing today.
   - The session root is the event's `cwd` when that is a string naming an existing directory, and `Path.cwd()` otherwise.
   - `-I` does not change the process cwd, so this is not needed for the fix itself. It is here because the event is the harness's own statement of where the session is. It also keeps the hook correct the day a launcher runs it from elsewhere (#220).

## Verification method: suite

- **The red test.** Run `factory-hook.sh session-start` through bash, as `test_hook_wiring.py` does, with the process cwd set to a temporary directory. That directory holds a `factory/` package whose `__main__` prints a sentinel and exits 0. Assert the sentinel never appears, **and** that the output carries the heartbeat `factory gates: LIVE`. The heartbeat assertion is what separates "the real factory answered" from "nothing answered". The test skips when no venv interpreter can be found, as the other bash-run tests do.
  - Today, `-m` imports the shadow first, so the sentinel prints. **Red.**
  - With `-I`, the installed package runs. **Green.**
- **The `cwd` test.** Based on `test_the_pre_tool_use_hook_still_reaches_the_session_row`. The process runs in an unrelated directory, and the event carries `"cwd": <builder worktree>`. Writing a sibling non-ticket worktree must be denied, citing ticket 5.
  - Today the session is the unrelated directory, so the hook prints nothing. The test asserts the output is non-empty before parsing it, so the red reason reads as "no decision", not as a JSON error. **Red.**
- **Also:** the same `cwd` rule for `stop`. A `cwd` naming a missing directory falls back to the process cwd. A terminal on stdin reads nothing (tested by injecting `isatty`). A copy of `factory-hook.sh` run from a directory with no `.git` and no `.venv` prints the unreachable message and exits 0.

## Decisions I made

- **No change to which venv the script finds.** It already prefers the session's own `.venv` and falls back to the primary checkout's. A worktree with its own `.venv`, and an editable install pointing at itself, would still judge itself. No worktree has one today, and creating one is a deliberate act. I name it under Could not verify rather than adding a refusal for a state that does not exist.
- **The hook script and `settings.json` are still read from the worktree** (`CLAUDE_PROJECT_DIR`), so a worktree can edit its own hook launcher. The design moves that defence into the factory loop's fingerprint (§4 rule 2), not this ticket.

## Recorded against the issue

- **The documentation lives in `factory/AGENTS.md`, not `docs/factory/README.md`.** The issue asks for `README.md`'s description of how the hook finds its interpreter. README has none; `factory/AGENTS.md` owns how the package runs, and it currently says hooks call the console script, which has not been true since #199. That sentence is corrected here.

## Could not verify

- **That the primary checkout is up to date.** After this change, the gate is whatever code the primary checkout has checked out. If it is behind, the hooks enforce stale rules. #159's heartbeat (re-check h) will print the primary's HEAD. Until then, keeping it current is the maintainer's habit.
- **That the event's `cwd` ever differs from the hook process's cwd**, for example after a `cd` inside a Bash call. That is harness behaviour, not checkable offline. The change is correct either way, because both fall back to the same place.
- **A consequence worth saying:** after this lands, bash-run hook tests executed in a ticket worktree exercise the **primary checkout's** `factory/`, not the branch's. The in-process tests (`main_cli([...])`) still test the branch. That is the point of the change, and it is why the red test asserts on the script and not on the branch's code.

## Not in scope

- `_stop_everywhere` judging every worktree (#207).
- The heartbeat printing the primary checkout's HEAD (#159, re-check h).
