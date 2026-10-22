---
ticket: 216
stage: build
radius:
  - .claude/hooks/factory-hook.sh
  - factory/cli.py
  - factory/AGENTS.md
  - tests/test_factory/test_cli.py
  - tests/test_factory/test_hook_wiring.py
  - .factory/216/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_hook_wiring.py::test_a_factory_package_in_the_session_cwd_cannot_answer_for_the_gate
  red_output_sha: 799fc0138c55
  suite: pass
docs_cleared: []
---

# Plan: the hook runs the main checkout's gate code

## Radius

| Path | Why |
| --- | --- |
| `.claude/hooks/factory-hook.sh` | `-I` on the exec line, with the reason in a comment |
| `factory/cli.py` | `_run_hook` reads the event once; `_read_event` (terminal guard) and `_session_root` |
| `factory/AGENTS.md` | "How it runs" and "The hooks": which code a hook runs; the console-script sentence corrected |
| `tests/test_factory/test_hook_wiring.py` | the shadow red test, and the copied-script unreachable test |
| `tests/test_factory/test_cli.py` | the `cwd` tests for pre-tool-use and stop, the missing-directory fallback, the terminal guard |

**Not in the radius:**
- `factory/hooks.py`. No decision changes. If it needs changing, this plan is wrong.
- `.claude/settings.json`. The command string is unchanged; only the script it runs changes.

Both of these files are protected paths. `.claude/**` is outside the merge allowlist, so this PR is a human merge regardless of type.

## Order of work

1. Write the red tests. Run them against the unchanged code and record the failures.
2. Change the script and `cli.py`. Run the tests green.
3. Update `factory/AGENTS.md`.
4. Run the full suite unmodified.

## Two notes from the passing spec review, taken here

- **The red test's skip is its own.** The other bash-run tests skip only without bash. This one also needs an interpreter that `factory-hook.sh` can find, so it searches the same two places the script does: this checkout's `.venv`, then the main checkout's. It skips only when neither exists. It **fails**, rather than skipping, if the hook prints `unreachable` while an interpreter does exist.
- **The event's `cwd` wins when it names a directory.** If it differs from the process cwd, the session root moves to it. Whether the two ever differ in a real session is unverified, and the PR body says that rather than "both fall back to the same place".

## Proof

**Red, before the change**: the two red tests, run against `2d14efb` (tests added, source untouched):

```
E       AssertionError: the session's own factory package answered
E       assert 'SHADOW-FACTORY-ANSWERED' not in 'SHADOW-FACTORY-ANSWERED\n'
E
E         'SHADOW-FACTORY-ANSWERED' is contained here:
E         Strings contain only whitespace, escaping them using repr()
E           'SHADOW-FACTORY-ANSWERED\n'
tests\test_factory\test_hook_wiring.py:195: AssertionError
E       AssertionError: the hook made no decision
```

The shadow test failed because the fake package answered. The `cwd` test failed because no decision was made at all. `test_the_stop_hook_takes_the_session_from_the_event_s_cwd` was red too. The terminal and missing-directory tests passed before the change: they guard behaviour the change introduces (every event now reads stdin), and do not prove the fix.

**Green, after**: `pytest` from the worktree root gave `1203 passed, 3 skipped, 25 deselected`, with 0 failed, 0 errors, 0 xfailed. `ruff check` and `ruff format` are clean on the changed Python files, and pre-commit (ruff, pyright) passed on commit `6fd973c`.

## Could not verify

- **That the primary checkout is current.** After this change, the gate is whatever code the main checkout has checked out.
- **Whether the event `cwd` ever differs from the process cwd in a real session.** When it does, the event `cwd` wins.
- **The shadow test only shows something on a machine whose venv sits in the main checkout.** That is the only setup in use. A worktree with its own `.venv` and editable install would still judge itself; none exists.
