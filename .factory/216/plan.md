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
  red_output_sha: see Proof below
  suite: null
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
