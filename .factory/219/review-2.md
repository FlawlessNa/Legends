---
ticket: 219
stage: review
cycle: 2
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: b5a334eb5919a5f84d4f89e1a4c5b5be752de46a
---

# Review, cycle 2: the factory loop's state outside the worktrees, and `factory park`

**Verdict: `pass`.** I checked only F1 to F4 from `review.md`, against
`b5a334e`. All four are resolved. F5 was a note that asked for no change, and
none was made.

Since `2265fb8`, the source diff is `factory/state.py` (+5 −1) and
`tests/test_factory/test_state.py` (+29). Both are inside the radius. No
existing test changed.

## Findings

| Finding | Status | Evidence |
| --- | --- | --- |
| F1: non-UTF-8 `state.json` escaped as `UnicodeDecodeError` | resolved | See F1 below. |
| F2: `render_run_md` docstring claimed too much | resolved | See F2 below. |
| F3: `fsync` untested | resolved | See F3 below. |
| F4: stale temp files never removed | resolved | See F4 below. |

### F1

- **The fix.** `_read` now adds `except UnicodeDecodeError` and raises `StateError(f"{path}: not valid UTF-8: …")`. The message names the file.
- **The new test.** `test_a_file_that_is_not_utf8_raises_state_error_naming_the_file` writes `b"\xff\xfe\x00{"`.
  - **Red without the fix:** I removed the two-line `except` and the test failed with `E UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`.
  - **Green with the fix.**
- **My original probe** (`b'\xff\xfe{bad'`) now gives `StateError: …state.json: not valid UTF-8: …`.

### F2

The docstring now says that `chain.front_matter` reads back `cycles.<stage>` only
for stage names made of identifier characters. It names `spec-review` as a key it
skips, and it says that nothing reads `run.md` back. That matches `_SCALAR`
in `chain.py`.

### F3

- **The new test.** `test_save_fsyncs_the_temporary_file_before_it_replaces_state_json` wraps `state.os.fsync` and `state.os.replace`, and asserts the events are exactly `["fsync", "replace"]`. The assertion checks order as well as presence.
- **Red without fsync:** I removed `os.fsync(handle.fileno())` and the test failed with `assert ['replace'] == ['fsync', 'replace']`.
- **Green with fsync.**

### F4

`plan.md`'s "Could not verify" section now says that a killed process leaves
`state.json.tmp-<pid>`. It also says the file is never read and never shadows
`state.json`, and that pruning it belongs to #210. The "Review fixes" section
records all four fixes, with their red outputs.

## Gates, at `b5a334e`

| Gate | Result |
| --- | --- |
| `pytest -q -p no:cacheprovider`, from the worktree root | `1573 passed, 3 skipped, 25 deselected`. 0 failed, 0 errors, 0 xfailed. |
| `ruff check` / `ruff format --check`, on the 5 changed `.py` files | clean / "5 files already formatted" |
| `pyright --pythonpath …/python.exe`, on the same files | `0 errors, 0 warnings, 0 informations` |

I restored `factory/state.py` from HEAD after each mutation. `git status`
shows only this file.

## What I could not verify

- **The #210 comment.** I did not open GitHub, per instruction.
- **Carried over from `review.md`:**
  - the `fcntl` branch;
  - fsync reaching the device;
  - a real worker running `factory park`;
  - the concurrent test's red on a heavily loaded machine.

Nothing here changes which keys reach the game.
