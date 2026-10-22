---
ticket: 216
stage: design
method: suite
criteria:
  - run the way factory-hook.sh runs it, from a directory holding a factory package that would answer differently, the hook returns the installed factory's answer and never the shadow's
  - the hook resolves factory through the interpreter's installed packages, with the current directory kept off the import path
  - every hook event takes its session root from the event's cwd field when that names an existing directory, and falls back to the process cwd otherwise
  - a pre-tool-use event whose cwd is a linked ticket worktree is judged with that worktree as the session, even when the process runs in an unrelated directory
  - a hook that cannot find an interpreter still prints its unreachable message and exits 0, unchanged from #199
  - every existing test in tests/test_factory passes unmodified
  - factory/AGENTS.md says which code a hook runs, and why the current directory is kept off the import path
specified_by: claude
specified_at: 2026-10-22
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

- **The red test.** Run `factory-hook.sh` through bash, as `test_hook_wiring.py` does, with the process cwd set to a temporary directory. That directory holds a `factory/` package whose `__main__` prints a sentinel and exits 0. Assert the sentinel never appears.
  - Today, `-m` imports the shadow first, so the sentinel prints. **Red.**
  - With `-I`, the installed package runs. **Green.**
- **The `cwd` test.** Based on `test_the_pre_tool_use_hook_still_reaches_the_session_row`. The process runs in an unrelated directory, and the event carries `"cwd": <builder worktree>`. Writing a sibling non-ticket worktree must be denied, citing ticket 5.
  - Today the session is the unrelated directory, so the answer is indifferent. **Red.**

## Decisions I made

- **No change to which venv the script finds.** It already prefers the session's own `.venv` and falls back to the primary checkout's. A worktree with its own `.venv`, and an editable install pointing at itself, would still judge itself. No worktree has one today, and creating one is a deliberate act. I name it under Could not verify rather than adding a refusal for a state that does not exist.
- **The hook script and `settings.json` are still read from the worktree** (`CLAUDE_PROJECT_DIR`), so a worktree can edit its own hook launcher. The design moves that defence into the factory loop's fingerprint (§4 rule 2), not this ticket.

## Not in scope

- `_stop_everywhere` judging every worktree (#207).
- The heartbeat printing the primary checkout's HEAD (#159, re-check h).
