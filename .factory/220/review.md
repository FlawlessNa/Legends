---
ticket: 220
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 0b16e85d99aa46f606b3477c935230af78bef741
---

# Review: the launcher, with herdr behind it

**Verdict: `changes-requested`.**

The work is careful and mostly complete. I checked 25 criteria:

- 22 are met;
- criterion 12 is met under the deviation recorded in the plan, which I accept;
- criterion 14 is not met in its general form (finding 1);
- criterion 23 is met to the letter, but one §12 claim is wrong (findings 2 and 3).

The red proof is real, and I re-ran it. The suite, ruff and pyright are clean.

The two findings that need a fix are both small:

- an unexpected reply shape after the split leaks the pane;
- `pane split` without a target falls back to the user's focused pane, which herdr's own guidance says not to rely on.

I reviewed `git diff 35ace7e..HEAD -- . ':!.factory'` and the chain. HEAD is `0b16e85`.

## What I ran

All runs were from the worktree root. Every source mutation was restored with `git checkout --`, and afterwards `git status --short` showed a clean worktree.

- **Full suite.** `python -m pytest -q -p no:cacheprovider` gave `1330 passed, 3 skipped, 25 deselected` in 108 s, with 0 failed, 0 errors and 0 xfailed. That matches the plan's figure. The flaky #229 test passed on this run.
- **Ruff.** `ruff check` and `ruff format --check` on the six Python files report "All checks passed!" and "6 files already formatted".
- **Pyright.** `pyright --pythonpath C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe` on the same six files gives 0 errors, 0 warnings.
- **Red proof, before the source existed.** I moved `factory/launcher.py` and `factory/launchers/` aside. Both test modules then fail at collection with `ModuleNotFoundError: No module named 'factory.launcher'`. Restored.
- **Red proof, the claimed mutation.** I deleted `"GIT_ASKPASS": ""` from `stripped_credentials`. `test_launcher.py` gave `21 failed, 28 passed`, including `test_worker_spec_carries_all_eight_credential_variables_for_every_role` for all five roles. That is exactly the plan's claim. Across both modules it gave 52 failed.
- **Per-variable drop inside `worker_spec`.** I also mutated `worker_spec` itself, so that it filters out one variable while `stripped_credentials` stays whole. That tests the criterion-5 wording more directly. The per-role test went `5 failed` for each of the eight variables in turn.
- **Further mutations.** Each was run against both modules, and each turned the suite red:

  | Mutation | Failed |
  | --- | --- |
  | Accept any option numbers | 2 |
  | Drop the prompt-seen rule in `status` | 2 |
  | Drop the `shell_pid`-in-table check | 1 |
  | Drop the own-pane guard | 1 |
  | Drop `--no-focus` | 1 |
  | Drop the back-pointer compare | 1 |
  | Drop the linked-worktree check | 1 |
  | Re-raise post-split errors without the Handle | 20 |
  | Make `pane_not_found` raise | 1 |
  | The fake skips `check_credentials` | 17 |
  | Allow a non-empty `GH_CONFIG_DIR` | 1 |

- **The real-binary guard.** An autouse fixture replaces `herdr_module.default_runner` with a function that raises. `HerdrLauncher.__init__` reads that module global when it is constructed, so the patched value is what it gets. `test_the_guard_fails_a_test_that_reaches_the_real_binary` builds an adapter with no runner and sees the `AssertionError`. Only `default_runner` calls `subprocess`, and `test_launcher.py` never builds a `HerdrLauncher`. No test reached herdr. I ran only `--help`, `herdr --skill` and `--version` myself, and created no pane or agent.

## Criteria

| # | Criterion (short) | Result | Evidence |
| --- | --- | --- | --- |
| 1 | WorkerSpec, Handle, WorkerState, Launcher shapes | met | `test_the_shapes_have_exactly_the_agreed_members` uses `typing.get_protocol_members`; `test_the_specs_and_handles_are_frozen` |
| 2 | name pattern; resume only for designer; read-only env copy | met | the name and resume tests; `MappingProxyType(dict(env))` at `launcher.py:105`; `test_the_spec_keeps_its_own_read_only_copy_of_env` |
| 3 | exactly eight variables; `GH_CONFIG_DIR` created under the common dir | met | `test_stripped_credentials_are_exactly_these_eight`. See finding 5 for a relative common dir. |
| 4 | a non-empty `GH_CONFIG_DIR` raises | met | `test_stripped_credentials_raises_for_a_non_empty_directory`; mutation M12 |
| 5 | `worker_spec` carries all eight for every role, and goes red per variable | met | re-ran: drops in either `stripped_credentials` or `worker_spec` go red for each of the eight |
| 6 | `start` refuses a missing or wrong variable before anything, on both launchers | met | the fake has parametrized missing and different-value tests for all eight, plus another common dir. The adapter has `test_start_refuses_missing_credentials_before_any_command`, with `herdr.calls == []`. The adapter test covers one variable only, but both launchers call the same `check_credentials` first (`fake.py:242`, `herdr.py:237`). |
| 7 | fake: records in order, scripted states repeating the last, session ids | met | the three fake tests |
| 8 | idempotent `start` on both launchers; a found agent gives a not-seen Handle with no split, start, prompt or keys | met | `test_a_second_start_on_the_same_launcher_returns_the_first_handle`; `test_a_fresh_launcher_that_finds_the_agent_starts_nothing` asserts `calls == [agent get]` |
| 9 | `status` by pane id; the mapping; not-seen idle and done read as blocked | met | `test_status_maps_each_herdr_state` has ten rows, each asserting `agent get <PANE>` |
| 10 | unknown code, non-JSON reply and unknown status raise | met | `test_status_raises_for_anything_it_cannot_map`; `test_a_reply_that_is_not_json_raises_wherever_it_arrives`. For a JSON reply of the wrong shape, see finding 1. |
| 11 | exact command sequence, argument lists, no shell | met | `test_start_issues_split_agent_start_and_prompt_in_order` compares the full argument lists; `shell=False` at `herdr.py:88`; resume and `--` tests. Targeting is under finding 2. |
| 12 | trust dialog: read, normalise, one `down enter`, bounded wait, prompt only after idle or done | met, with the recorded deviation | See *The trust dialog* below. Tests use the committed live capture and six constructed variants. |
| 13 | linked-worktree pairing; relative, outside and back-pointer cases tested | met | Tests exist for all of these. I also checked it against real git (below). |
| 14 | every error after a successful split carries the Handle | **not met in general** | All the enumerated cases are tested and pass. A JSON reply of the wrong shape escapes as `AttributeError` with no Handle (finding 1). |
| 15 | `session_id` from `agent list` by pane id | met | four rows: id, path, null, no match |
| 16 | `stop` raises with no herdr call for a designer (both launchers) and for its own `HERDR_PANE_ID` (adapter) | met | `test_stop_refuses_a_designer_and_issues_nothing` and `..._launchers_own_pane_...` assert `calls == []`; the fake's designer test |
| 17 | `stop` closes only the Handle's pane id | met | `test_stop_closes_only_the_handles_pane_and_waits_for_the_tree` checks the exact calls |
| 18 | `pane_not_found` means already stopped, idempotently | met | `test_a_pane_herdr_no_longer_has_counts_as_stopped_and_stop_is_repeatable` |
| 19 | `shell_pid` required in the pre-close snapshot; tree recorded; bounded wait; empty-table test | met | `herdr.py:300-307`; `test_stop_cannot_pass_on_an_empty_process_table`; descendant and shell timeout tests. See finding 6 on the reader. |
| 20 | `status` is gone after `stop`, on both launchers | met | `test_after_stop_returns_status_is_gone` asserts no further herdr call; the fake's equivalent |
| 21 | Toolhelp reader: lists this process and its parent on Windows, raises elsewhere, never raises on import | met | ran on Windows: `table[getpid()] == getppid()`; the `sys.platform` monkeypatch test; the subprocess import test |
| 22 | fixtures only; provenance table; trimmed; guard | met | `PROVENANCE` plus a test that fails on any untabled file; the guard verified as above. `agent_get_idle_other_pane.json` is unused (note b). |
| 23 | design §8 and §12 | met to the letter, inaccurate in part | See findings 2 and 3. |
| 24 | only the allowed files change; `merge.py`, the protected set and `pyproject.toml` unchanged | met | `git diff --name-only 35ace7e..HEAD` and `9654223..HEAD -- pyproject.toml factory/merge.py` are empty for those paths. See *Packaging*. |
| 25 | pytest, ruff, pyright clean | met | see *What I ran* |

## The trust dialog

**The deviation.** Criterion 12 asks for options "numbered n" and "n+1". The committed live capture, `trust-dialog-live.txt`, has no numbers:

```
❯ No, exit
  Yes, I trust this folder
```

The matcher is `…you trust\?.*?(?:(\d+)\. )?No, exit (?:(\d+)\. )?Yes\b`, followed by a check on the numbers:

- no numbers on either option: accepted;
- numbers on both options: accepted only when they are consecutive;
- a number on one option only: refused.

I accept the deviation. Without it, the one recorded live layout would be refused. It also loses nothing the numbered rule protected: the matcher still accepts only "No, exit" immediately followed by "Yes".

**Crafted variants.** I ran 20 variants through `trust_dialog_matches`. Each screen the spec meant to refuse is refused:

- "Yes" listed first, numbered or not, with the cursor marker or without;
- the cursor marker on Yes, as `❯` or ASCII `>`, with numbers or without;
- a third option between the two;
- numbers that are not consecutive: `1/3`, `1/1` and `2/1`;
- `1)`-style numbers;
- "Yesterday" in place of an option;
- the MCP approval screen;
- a "No, exit / Yes" pair with no trust question.

The live screen still matches with CRLF line endings, with a non-breaking space inside "No, exit", and when the question wraps.

**One permissive case remains.** The span between the question and the options is unbounded. A trust question with "Yes" listed first, followed later in the same read by another screen that has "No, exit" directly above "Yes", is accepted. The spec's own wording ("contains … followed by") permits this too, and it needs two dialogs in one recent-unwrapped read of a fresh pane. I record it as note a, not as a finding.

**Not a linked worktree.** `test_the_trust_dialog_outside_a_linked_worktree_is_not_answered` sends no keys and no prompt, and raises with the Handle. Mutation M8 turns it red.

**Worktree identity.** `is_linked_worktree` gave the expected answer in every case:

| Case | Result |
| --- | --- |
| This worktree, with a forward-slash `.git` file and back-pointer, and absolute paths | True |
| The same, written with forward slashes | True |
| The same, lower-cased | True |
| The same, with a relative common dir `.git` from the main checkout | True |
| A fresh `git worktree add` (git 2.39) | True |
| That worktree, given relative paths | True |
| That worktree, rewritten with relative `gitdir` and back-pointer, as git 2.48 `--relative-paths` writes them | True |
| A relative back-pointer that does not match | False |
| A `gitdir` one level deeper than `worktrees/<id>` | False |
| The main checkout | False |

Paths are compared as resolved `Path` objects, so Windows case and slash differences are harmless.

## Pane leaks and the prompt race

Every enumerated failure after the split carries the Handle and sends no extra keys. Mutation M9 turns 20 tests red.

Every herdr wait carries a timeout:

- `agent start --timeout 60000`;
- `agent wait --timeout 30000`;
- `agent prompt --timeout 60000`;
- `stop` polls for 30 s.

The client side is unbounded (finding 4).

**Prompt race.** A Handle gets `prompt_started=True` only after `agent prompt --wait --until working --until blocked` returns success (`herdr.py:252`). A replayed or found Handle is `False`, and `status` maps idle and done to blocked for it. Mutation M3 turns this red. `status` cannot report finished before the prompt was seen to start.

## `stop`

The guard order is correct:

1. A designer raises.
2. `HERDR_PANE_ID` raises. Both happen before any herdr call. The format matches: my own pane reads `w1:p5`.
3. `pane_not_found` from `process-info` returns, and records the pane as gone.
4. `shell_pid` must be an int and present in the pre-close snapshot.
5. The tracked set is the shell pid, the foreground pids and their descendants.
6. The pane is closed. `pane_not_found` on close is tolerated.
7. Fresh snapshots are polled until none of the tracked pids appears, or the call raises at the deadline.

**The Toolhelp reader.** The structure layout matches `PROCESSENTRY32W`: `th32DefaultHeapID` is `ULONG_PTR`, written as `c_size_t`, and `szExeFile` is `WCHAR[260]`. The `INVALID_HANDLE_VALUE` comparison is correct for a `c_void_p` return. The platform guard comes before the `ctypes` import, and importing the module never raises. One weakness is finding 6.

## `pane split` with no target

`herdr --skill` (0.9.5) says:

> "An omitted `pane split` target uses the calling pane when `HERDR_PANE_ID` is available, otherwise the focused pane."

Its safety rules add:

> "Use `--current`, an explicit pane ID, or a unique agent name. Do not rely on another client's focused pane."

`default_runner` passes the parent environment through. Inside the loop's own pane (design R2), `HERDR_PANE_ID` is therefore set, and each worker splits the loop's pane. That works, but it is implicit.

Outside a herdr pane, the split lands in whatever pane the maintainer has focused. That can be in another workspace. Nothing fails closed there. This is finding 2.

## Packaging and the protected set

`pyproject.toml` still reads `packages = ["factory"]` and is unchanged. The maintainer action and the exact replacement line are in the spec and the plan, for the PR body.

The import closure of `factory.__main__` and `factory.cli` does not import `factory.launcher` or `factory.launchers`. A grep of the closure modules finds no import of either. So `test_every_module_the_console_script_imports_is_protected` is unaffected, and it passes in the suite. CI installs in editable mode, so the subpackage imports there.

## Findings

### 1. A reply of an unexpected shape after the split leaks the pane (criterion 14, medium)

`_answer_trust_dialog` reads `read.get("read", {}).get("text", "")` at `herdr.py:391`. When `result.read` is `null`, or is not an object, this raises `AttributeError`. `start` re-wraps only `LauncherError` (`herdr.py:250-251`), so the error escapes with no Handle, after a successful split. The loop cannot stop that pane. Criterion 14 says *every* error after a split carries the Handle.

I drove the adapter with stored replies plus one crafted reply:

```
agent read result.read = null  -> AttributeError (no handle)
agent read result.read = "x"   -> AttributeError (no handle)
```

`stop` has the same class of problem, though there it raises rather than passing, so it is safer:

```
process_info = null            -> AttributeError
foreground_processes = [5]     -> AttributeError
```

That breaks criterion 10's spirit that nothing herdr says is guessed at: these should be `LauncherError`.

**Fix:**

1. Type-check `result["read"]` before using it. Do the same for `process_info` and each `foreground_processes` entry in `stop`, and for each `agents` entry in `session_id`. Raise `LauncherError` on a wrong shape.
2. As a backstop, have `start` convert any non-`LauncherError` exception after the split into `LauncherError(..., handle=handle)`.
3. Add a test with `{"read": null}` that asserts `error.handle == handle_for(spec)` and that no keys were sent.

### 2. `pane split` relies on herdr's implicit target, and §12 misdescribes the failure (medium)

The plan's *Could not verify* and §12 both list "which pane `pane split` divides when given no target" as unverified. §12 adds "Either failing stops every dispatch, closed."

herdr's bundled skill documents the behaviour, quoted above. The fallback does not fail closed: without `HERDR_PANE_ID`, workers open in the user's focused pane, against herdr's own safety rule.

**Fix:**

1. Read `HERDR_PANE_ID` from the injected `environ`, which is already there for `stop`.
2. If it is unset, raise `LauncherError` before any split. No Handle exists yet, so nothing leaks.
3. Otherwise pass it explicitly as `pane split --pane <id> --no-focus …`.
4. Add a test for each case.

Criterion 11 does not forbid a target, so this stays within the spec. Update §12 and the PR's *Could not verify* to match. What remains unverified live is only how repeated splits of the loop's pane behave. The skill warns against repeated same-direction splits, so consider a `--direction` too.

### 3. design.md §8 and §12: accuracy (low)

- **§12, the pane-split bullet.** It is wrong as written; see finding 2. The pane-id-during-`agent_not_ready` half of that bullet is accurate and should stay.
- **§8, the deleted open questions.** §8 deletes "Open questions, answered by #215" and §12 deletes "The five launcher questions". Only two answers now appear in the design: env reaches the worker through repeated `--env`, and the folder-trust dialog. The answers to "which permission mode", "do hooks fire in that mode" and "does a worker's Bash have a terminal" are recorded nowhere. The spec carries one of them: workers inherit auto mode. Add one line to §8 giving #215's answers, or at least pointing to them. Otherwise the design loses facts it used to say it would have.
- **§8, the `status` bullet.** It says "`idle` and `done` are finished" without the prompt-not-seen exception. The `start` bullet does state it. A clause in the `status` bullet would keep it self-contained. This is optional.

### 4. Client-side calls to herdr are unbounded (low)

`default_runner` calls `subprocess.run` with no `timeout`. The four herdr-side waits are bounded by their own `--timeout`. Every other call has no bound: `agent get`, `agent list`, `pane split`, `agent read`, `send-keys`, `process-info` and `pane close`.

If the herdr server wedges, the loop blocks forever. The loop is long-lived and "never exits on its own" (R2), so it would stall with no error.

**Fix:** pass a `timeout` to `subprocess.run`: the command's own `--timeout` plus a margin, or a fixed value for the other commands. Map `subprocess.TimeoutExpired` to `LauncherError`. `TimeoutExpired` is not an `OSError`, so the current `except` would not catch it.

### 5. A relative common dir gives a relative `GH_CONFIG_DIR` (low)

`stripped_credentials` returns `str(common_dir / GH_CONFIG_SUBPATH)` without resolving it. `chain.git_dir(Path("."))` in the main checkout returns `.git`, which is relative.

A relative value is read against the worker's cwd, which is a different worktree. That breaks "a directory under the git common dir" (criterion 3). It does not leak a credential, because `GH_TOKEN` still wins.

**Fix:** resolve `common_dir` in `stripped_credentials`, and in both launchers' constructors. Add a test with a relative common dir.

### 6. The Toolhelp reader treats any enumeration failure as the end of the list (low)

`Process32FirstW` or `Process32NextW` returning FALSE ends the loop without checking `GetLastError() == ERROR_NO_MORE_FILES` (18).

The pre-close snapshot is protected, because `shell_pid` must be present. A failed post-close snapshot, though, returns a short or empty table, and `_wait_for_exit` reads that as everything having exited. That is a vacuous pass.

This is rare, but the spec's "cannot pass vacuously" reasoning applies. **Fix:** raise `OSError` unless the last error is `ERROR_NO_MORE_FILES`.

## Notes, not findings

- **a.** The trust match spans the whole read, with no bound between the question and the options. See *The trust dialog*. Bounding the options to the question's own screen, for example with no "Enter to confirm" between them, would close it. The spec does not require this.
- **b.** `agent_get_idle_other_pane.json` is in `PROVENANCE`, but no test uses it. Use it or delete it.
- **c.** The live capture came from a probe folder whose settings "pre-approve 2 tool permissions". This repository's `.claude/settings.json` has hooks and no `permissions`. A Legends worktree may therefore show a different layout of the trust dialog. If "Yes" is listed first, every first dispatch into a fresh worktree fails closed. Spec review cycle 1 attributed the layout to hooks. The fixture text says permissions. The PR's human actions should keep "capture the dialog once in a real Legends worktree before #223".
- **d.** After `stop`, a `start` on the same launcher with the same name returns the stopped Handle and starts nothing. This is consistent with criterion 8, and names are per attempt, but the loop should know it.

## What I could not verify

- Anything against a live herdr. I created no pane and started no agent, by instruction.
- Every herdr behaviour the plan already lists:
  - an empty `--env` value passing through;
  - pane-id targeting while startup is blocked;
  - `down enter` on a Legends worktree's dialog (note c);
  - closing a pane ending background descendants, and orphans;
  - Git Credential Manager by other routes.
- What herdr does when splits of the loop's pane are repeated, and whether `HERDR_PANE_ID` is set in the environment the loop will actually run in (#159).
- Whether gh writes into the empty `GH_CONFIG_DIR` during an ordinary failing call. If it does, every later `start` raises until a human empties the directory. That fails closed, but it would stop the factory.
- A non-Windows run of the import-safety test. I ran it on Windows with `sys.platform` patched in a subprocess, which is what the test does.
- Whether the constructed replies for mutating commands match what herdr 0.9.5 really returns. They were built from the schema, not captured.
