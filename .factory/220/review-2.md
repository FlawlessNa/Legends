---
ticket: 220
stage: review
cycle: 2
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 079979e
---

# Review, cycle 2: the launcher, with herdr behind it

**Verdict: `pass`.**

I checked only the six findings from `review.md`, against `079979e`. All six are fixed, and each fix has a test that fails without it. The suite, ruff and pyright are clean.

What remains is three notes. None needs to block the merge.

## What I ran

All runs were from the worktree root. Source swaps were restored with `git checkout HEAD --`, and afterwards `git status --short` showed only this file.

- **Full suite.** `python -m pytest -q -p no:cacheprovider` gave `1341 passed, 3 skipped, 25 deselected` in 113 s, with 0 failed, 0 errors and 0 xfailed. That matches the plan's figure.
- **Ruff.** `ruff check` and `ruff format --check` on the six Python files report "All checks passed!" and "6 files already formatted".
- **Pyright.** `pyright --pythonpath C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe` on the same files gives 0 errors, 0 warnings.
- **Red proof.** I checked out the pre-fix source from `0b16e85` (`factory/launcher.py` and `factory/launchers/`) and kept HEAD's tests.
  - On their own, the tests fail at collection, because `_collect_table` does not exist yet.
  - So I appended a shim to the old `herdr.py`. It is the pre-fix walk, which never checks the last error. With it, the two modules gave `11 failed, 133 passed`, listed in the table below.
  - Among the new tests, only `test_a_complete_enumeration_ends_on_no_more_files` passes on the old logic. That is expected: it is the positive case, and it is red before the fix only through the `ImportError`.
  - The builder's "12 red" count therefore includes one modified existing test, the exact `pane split` argument list, and that import-only red. This is accurate enough, and I note it only so the count can be read.
- **My cycle-1 probes, re-run against HEAD.**
  - A `read` of `null`, of a string, or with `text` set to `null` now gives a `LauncherError` that carries the Handle.
  - A `process_info` of `null`, and a non-object entry in `foreground_processes`, now give a `LauncherError` before any close.
  - With the cwd set to the common dir's parent, a relative common dir gives an absolute `GH_CONFIG_DIR`.

## The six findings

| # | Finding | Result | Evidence |
| --- | --- | --- | --- |
| 1 | A reply of the wrong shape after the split leaks the pane | fixed | `_answer_trust_dialog` checks the type of `read` (`herdr.py:468-469`). `start` now turns any non-`LauncherError` exception after the split into a `LauncherError` with the Handle (`herdr.py:303-308`). `stop` checks `process_info` and each foreground entry; `session_id` checks each `agents` entry. Red without the fix: `test_a_screen_read_of_the_wrong_shape_carries_the_handle`, `test_any_exception_after_the_split_becomes_a_launcher_error_with_the_handle`, and `test_a_process_info_of_the_wrong_shape_raises_a_launcher_error` for both of its cases. |
| 2 | `pane split` relies on herdr's implicit target | fixed | `_split` reads `HERDR_PANE_ID` from the injected `environ`. If it is unset or empty, `_split` raises before any split, with no Handle. Otherwise it passes `--pane <id>`. Red without the fix: `test_the_split_names_the_loops_own_pane_as_its_target`, `test_start_raises_before_splitting_when_the_loop_has_no_pane`, and the updated exact-arguments test. §12 and the plan's *Could not verify* now name only the live unknown, how repeated splits of the loop's pane behave, and no longer claim the split fails closed. |
| 3 | design §8 and §12 accuracy | fixed | §12's bullet is corrected, as above. §8 gains "What #215 answered besides the launcher": workers inherit auto mode, hooks fire in that mode, and a worker's Bash terminal is unreliable (`GetConsoleMode` fails; see #222). The spec's table confirms the first; I could not check the other two against #215 (below). The `status` bullet now states the exception for a prompt not seen to start. |
| 4 | Client-side calls to herdr are unbounded | fixed | `default_runner` passes `timeout=_client_timeout(args)`: the command's own `--timeout` plus 15 s, or else 30 s. It maps `subprocess.TimeoutExpired` to `LauncherError`. I probed the bounds: `agent get` gets 30 s, and `agent start --timeout 60000` gets 75 s. Red without the fix: `test_the_real_runner_bounds_every_call_in_time` and `test_the_real_runner_turns_a_client_timeout_into_a_launcher_error`. |
| 5 | A relative common dir gives a relative `GH_CONFIG_DIR` | fixed | `stripped_credentials` resolves `common_dir`, and both launchers resolve it in their constructors, so `check_credentials` compares like with like. Red without the fix: `test_a_relative_common_dir_still_gives_an_absolute_gh_config_dir`, which also starts a `FakeLauncher` built from the relative path. |
| 6 | The Toolhelp reader treats any enumeration failure as the end of the list | fixed | `_collect_table` raises `OSError` unless the last error is `ERROR_NO_MORE_FILES` (18). `ctypes.get_last_error` reads the value the final `Process32NextW` left, because nothing in between calls into Windows. The real-reader test on Windows still passes, so the live walk does end on 18. Red without the fix: `test_a_failed_enumeration_raises_rather_than_ending_the_list`. |

The unused fixture `agent_get_idle_other_pane.json` is deleted. The three new constructed fixtures are in `PROVENANCE`, and the completeness test passes.

## Notes, not findings

- **a. The guard has a deliberate opening.** The test module now imports `default_runner` as `real_default_runner`, so that it can test the client timeout. Both callers patch `subprocess.run` first, so no test reaches herdr today. The autouse guard no longer covers that name, though. A future test that called it unpatched would run the real binary. Making the guard also patch `subprocess.run` to refuse any `herdr` command would close it.
- **b. `_client_timeout` reads the first `--timeout` in the argument list.** A prompt or agent argument that is literally `--timeout` would cut the bound to 30 s, below herdr's own 60 s. That fails closed: `LauncherError` with the Handle. Reading the last occurrence, or passing the timeout explicitly, would avoid it. It is contrived.
- **c. A client timeout during `pane split` can leave a pane the adapter never learned the id of.** This is the same class as the crash-before-`agent start` leak that the spec already accepts.

## What I could not verify

- **#215's other answers.** I did not touch GitHub, so I could not check §8's "hooks fire" and "`GetConsoleMode` fails" against #215's comments.
- **Anything live.** That includes `--pane <HERDR_PANE_ID>` on a real herdr, the client timeout margins, and repeated splits of one pane.
- **Everything already listed** in `review.md` and the plan under *Could not verify*. None of it changed.
