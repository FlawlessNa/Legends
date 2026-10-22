---
ticket: 216
stage: review
cycle: 2
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 5cc7de4c7bd2834b522500c11afc3614046f78b2
---

# Review, cycle 2: the hook runs the main checkout's gate code

**Verdict: `pass`.** I checked only the four findings from `review.md`, against
`git diff 533ba42..5cc7de4`. F1, F2 and F3 are resolved. F4 needed no change.
Two small notes are left at the end, and neither blocks.

## What I ran

All runs used `C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`, from the
worktree root.

- **`pytest -q -p no:cacheprovider`:** `1204 passed, 3 skipped, 25 deselected`.
  0 failed, 0 errors, 0 xfailed. That is one more pass than cycle 1: the new F1
  test.
- **`ruff check` and `ruff format --check`** on `factory/cli.py`,
  `tests/test_factory/test_cli.py` and `tests/test_factory/test_hook_wiring.py`:
  clean.
- **`pyright --pythonpath <venv python>`** on the same three files: 0 errors.
- **`bash -n .claude/hooks/factory-hook.sh`:** OK.

## F1. A subdirectory `cwd` silenced the Stop gate: resolved

`_session_root` now returns `governing(Path(cwd)).root` for a valid event
`cwd`. When no worktree governs it, it falls back to the directory as given.

**Red proof for the new test.** I checked out `factory/cli.py` at `533ba42`,
kept the tests, and ran
`test_a_cwd_inside_a_worktree_is_judged_from_the_worktree_root`. It failed with
`AssertionError: the hook made no decision`. On HEAD it is green. I restored
with `git checkout HEAD -- factory/cli.py`, and the tree was clean afterwards.

**My cycle-1 probe** (`probe_subdir2.py`), re-run on HEAD with the event `cwd`
set to `<wt>/botting`:

| Event | Cycle 1 (`533ba42`) | Now |
| --- | --- | --- |
| `stop` | no output | `{"decision": "block", "reason": "Source changed on ticket 5 but plan.md records no proof..."}` |
| `session-start` | "Not in a ticket worktree" | "You are on a factory ticket branch: ticket 5" |

Both now match the old behaviour with no `cwd` field.

`governing` returns a resolved, symlink-free root. That is the same form
`decide_write` already uses for the session, so the change adds no new kind of
path comparison downstream. The process-cwd fallback is still `Path.cwd()`,
unwalked. That is deliberate, and it is today's behaviour, so nothing got worse.

## F2. mintty and the `isatty` guard: resolved

The script now runs `[[ -t 0 ]] && exec </dev/null` before it looks for an
interpreter. Its comment names SKILL.md and mintty.

There is no `set -e`, so a false `-t 0` cannot end the script. The non-terminal
path is unchanged:
- piping `{}` into `pre-tool-use` exits 0;
- the wiring tests, which feed stdin through a pipe, pass in the suite.

On Windows, `/dev/null` reaches `python.exe` as `NUL`. `isatty()` may report
that as a terminal, but either branch of `_read_stdin` returns `{}` without
blocking.

## F3. The install caveats: resolved

`factory/AGENTS.md`'s paragraph "Which code a hook runs" now says three things:
- `-I` keeps the session's directory off the import path;
- the guarantee is only as good as the install, because an install made from a
  worktree points every session there, so install from the main checkout;
- without the install, `-I -m factory` fails with "No module named factory"
  rather than printing "unreachable".

That matches what I observed in cycle 1 (base interpreter, rc=1).

## F4. What the shadow test proves: no change, as agreed

## Notes, not findings

- **The F3 paragraph is now slightly contradictory.** The sentence before the
  new text still reads "It never runs a worktree's own copy, whatever
  directory the session sits in", and the new text then qualifies it. Fold the
  qualifier into that sentence if anyone touches the paragraph again. There is
  also a short line, "message. Plain `python -m` puts the", which is a reflow
  leftover.
- **The PR body should carry the cycle-1 Could-not-verify items.** These are:
  - the harness's process cwd versus the event `cwd`;
  - that SessionStart and Stop stdin is closed by the harness, since every
    event now reads to EOF;
  - mintty itself;
  - that this PR touches `.claude/**`, so a human merges it.

## What I could not verify

- **The terminal branch of `[[ -t 0 ]]`.** This session's stdin is
  `/dev/null`, and there is no pty tool on this machine, so I checked that
  branch by reading it, not by running it. Whether bash under mintty reports
  its pty as a terminal is known msys behaviour, but I did not test it here.
- **Anything new in harness behaviour.** The same unknowns as cycle 1 still
  apply.
