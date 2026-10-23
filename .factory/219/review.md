---
ticket: 219
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 2265fb8a7b2bfc30881b99c9594dac93c6905b95
---

# Review: the factory loop's state outside the worktrees, and `factory park`

**Verdict: `changes-requested`.** The work is sound: the lock, the atomic write,
the Windows retries and `park` all hold up under probes that go past the
builder's tests. One criterion has a gap. Criterion 2 says malformed JSON
raises `StateError`, but a `state.json` that is not valid UTF-8 escapes as a
bare `UnicodeDecodeError` (F1). The other findings are a docstring that claims
too much (F2), plus notes.

I reviewed `git diff eec1b8a..HEAD -- . ':!.factory'`: 8 files, all inside the
plan's radius. Probes ran from `C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`
on Windows 11, using scripts in a scratchpad. The source was restored after
each mutation, and `git status --short` is clean apart from this file.

## Gates

| Gate | Result |
| --- | --- |
| Full suite, from the worktree root, `-p no:cacheprovider` | `1571 passed, 3 skipped, 25 deselected`; 0 failed, 0 errors, 0 xfailed. Matches the plan. |
| The three ticket modules, 3 more runs | `113 passed` each time. The concurrent test was not flaky. |
| `ruff check` / `ruff format --check` on the 5 changed `.py` files | clean / "5 files already formatted" |
| `pyright --pythonpath …/python.exe` on the same 5 files | `0 errors, 0 warnings, 0 informations` |

## The red proof, re-run

- **`state.py` deleted and `cli.py` reverted to `eec1b8a`, tests kept.**
  - `test_state.py` fails to collect: `ImportError: cannot import name 'state' from 'factory'`.
  - `test_park.py`: 21 failed. 18 fail on `argparse.ArgumentError: … invalid choice: 'park'`. The 3 flag-misuse cases also fail their message check (`'required'`, `'not allowed with'`, `'expected one argument'` are not in the `invalid choice` text), so they do not pass merely because exit code 2 is shared.
  - The plan counts 23 because it also reverted the docs. I kept them, so the two docs tests passed.
- **The lock made a no-op** (the `msvcrt.locking` call in `_try_lock` replaced by `return`):
  - `test_two_processes_updating_at_once_lose_neither_update` failed **6 runs out of 6**, with `AssertionError: assert 1 == 2`, a lost update.
  - `test_the_lock_wait_is_bounded_then_state_error` fails with `DID NOT RAISE StateError`.
- **My own mutations of `state.py`** (named test → result):

  | Mutation | Test | Result |
  | --- | --- | --- |
  | `PermissionError` read as missing | `test_load_never_reads_a_permission_error_as_a_missing_file` | red |
  | no retry | the three retry tests | 3 red |
  | write `state.json` in place, no temp | interrupted write | red |
  | temp in another directory | interrupted write | red |
  | no log-append check | `…shortens_or_rewrites_the_log` | red |
  | `dispatched` never resets | `test_dispatched_…` | red |
  | `cycles` unsorted in both `__post_init__` and render | render order | red (either sort alone keeps it green, by design) |
  | version unchecked / unknown fields tolerated / `bool` as int | bad-file parametrisation | red each |
  | `cycles` mutable | read-only test | red |
  | **`os.fsync` removed** | interrupted write | **green**: see F3 |

## Criteria

| # | Criterion (short) | Met | Evidence |
| --- | --- | --- | --- |
| 1 | `<common>/factory/<n>/state.json` via `chain.common_dir`; `StateError` outside a repo | met | `state_path`. Tested in a linked worktree (`test_the_state_lives_in_the_common_dir_of_a_linked_worktree`) and outside a repo for both `load` and `update`, with no directory created. `repo_root` must be a worktree root, not a subdirectory, as with `common_dir` itself. |
| 2 | exactly 12 fields; `StateError` for missing/unknown/mistyped, a bad version, malformed JSON | **not met (F1)** | My probe got `StateError` for `version` `"1"`, `True` and `1.0`, for `ticket` `"7"`, for an extra key in `log[0]`, for an `accepted_at` that is an int, for `cycles {"review": true}`, for `parked ["x"]` and for an empty file. **Invalid UTF-8 raised `UnicodeDecodeError`, which names no file.** |
| 3 | fresh state values; fresh only when `state.json` does not exist | met | `_read` returns `fresh` only on `FileNotFoundError`. A directory at `state.json` (a `PermissionError` on Windows) gave `StateError`, not fresh. |
| 4 | `attempt` is 1-based per stage and resets; `cycles` per judged stage | met | `dispatched()` (note d, option i). The test covers 1, then 2, then a new stage at 1. |
| 5 | temp in same dir, flush, fsync, `os.replace`; killed process leaves previous state; stale temp never shadows | met | Code at `_save`. **I killed a real process** (`Popen.kill`, i.e. `TerminateProcess`) while it stalled inside `os.replace` after writing `state.json.tmp-<pid>`. `load` then gave the old state (`attempt 5, worker old`), and `update` took the lock 3 ms later. The stale temp was left in place and ignored. fsync is called but not tested (F3). |
| 6 | `PermissionError` retried a bounded number of times then `StateError`; never "missing" | met | Probe, a tight reader process against 300 `update`s: 0 `StateError`, 0 fresh misreads, at most 14 replace tries. Probe, `load` in a loop against a writer process doing 892 updates: 307 real `PermissionError`s on read, all retried, with 0 `StateError`, 0 fresh and 0 values going backwards. |
| 7 | `update` under an OS lock on `state.lock`, released on death; concurrent processes | met | See "The lock" below. |
| 8 | round trip equal; log only grows; `cycles`/`log` read-only | met | The round-trip tests. `update` refuses a shorter or rewritten log. `MappingProxyType` plus a tuple. |
| 9 | `render_run_md` deterministic; `cycles.<stage>` keys sorted; log table in order | met (F2 on the docstring) | `__post_init__` and render both sort. Equal states give equal text whatever the insertion order (test, plus mutation). |
| 10 | `--reason` → needs-human, `--question` → spec-gap; front matter; exactly one non-empty flag | met | `_configure_park` uses a required, mutually exclusive group. Whitespace-only text is exit 2. Tests cover each flag, neither, both, a missing value and empty text. |
| 11 | resolve via `worktree_for` or the session's worktree; never writes `state.json` | met | Tests, plus a probe: from a subdirectory of the ticket worktree, `park.md` lands at the worktree root. `<common>/factory` is never created. |
| 12 | stage = routing's at that moment, null when none or raises; still exit 0 | met | `except ValueError` covers `MalformedVerdict` and `UnknownChainVersion`, both `ValueError` subclasses. Blocked-chain and malformed-verdict tests give `stage: null` with exit 0. |
| 13 | exit 0/2/3 as listed; 3 without writing, naming the kind; design §9 row | met | Every code is tested. `open(…, "x")` makes the exit 3 race-safe. Probe: an existing park on a chain with a malformed verdict still gives 3, naming `needs-human`, because `read_chain` does not raise. The §9 row lists every code. |
| 14 | `read_chain(...).park` returns the front matter; `artifacts.md` contracts for `park.md` and `run.md` | met | `test_read_chain_returns_the_written_front_matter`, `test_artifacts_md_contracts_park_and_run` |
| 15 | `git status --porcelain --ignored` unchanged in every worktree; suite green | met | `test_state_never_changes_git_status_in_any_worktree` covers 3 worktrees. Suite above. |

## The lock

- **Released when the process is killed.**
  - One process held `state.locked(...)` and was killed with `Popen.kill`.
  - Before the kill, `update` with `LOCK_TIMEOUT = 0.5` raised `StateError` after 0.50 s, naming `state.lock`.
  - After the kill, `update` acquired the lock in 0.014 s.
  - The builder's "could not verify" on this point is now verified on Windows.
- **The bounded wait raises `StateError`.** Tested in process, and probed across processes (above).
- **The byte range on an empty file.** While `state.lock` was held, its size was 0 bytes.
  - From another handle, `msvcrt.locking(LK_NBLCK, 1)` at offset 0 was refused with errno 13.
  - The same call at offset 1 succeeded.
  - So `seek(0)` followed by a 1-byte lock covers exactly byte 0 past the end of an empty file. Every caller locks that same byte, so it is the right range.
- **`fcntl`** was not run. Its shape is correct: `flock(LOCK_EX | LOCK_NB)` raises `BlockingIOError`, which is an `OSError`, so the bounded loop catches it.

## `update`'s extra refusals

They are correct, and I found no over-refusal.

- **Renaming the ticket** would write ticket 8's state into ticket 7's file. `_parse` already refuses that on read, so refusing it on write keeps the file loadable.
- **The log check** is a prefix comparison of `LogEntry` dataclasses. Nothing normalises an entry between `_parse` and `_to_data`, so a true append always passes.
- I ran a realistic sequence through `update` and every step was accepted:
  - `dispatched` plus `with_log`;
  - a `cycles` bump plus `accepted` plus `parked`;
  - clearing `accepted` and `parked`.
- A state on disk that is corrupt makes every later `update` raise until a person repairs it. That is the strictness the spec asks for, not over-refusal.

## `render_run_md` and the hyphenated keys

`chain.front_matter`'s `_SCALAR` (`^[A-Za-z_][A-Za-z0-9_]*:`) skips `spec-review: 2`. The builder's test says so and checks the raw block instead.

- **For `run.md`, this is not a defect.** `artifacts.md` says "Nothing reads it back". The text holds one `cycles.<stage>` key per judged stage in sorted order, as nested YAML, which is what criterion 9 asks for.
- **`artifacts.md` makes no claim about `chain.front_matter`**, so its contract is accurate.
- **The `render_run_md` docstring does make that claim.** See F2.

## The changed test

`test_every_registered_command_is_reachable_through_the_parser` now passes `--reason x` for `park` only. The change is justified:

- A required mutually exclusive group cannot parse bare. That is what criterion 10 ("exactly one non-empty flag being required") demands.
- Every command is still parsed and its name checked.
- No other existing test changed. The diff touches only `test_cli.py` among the existing tests.

## The docs

- **design §9.** The `park` row gives `[<n>]`, every 2 and 3 cause, and the worktree. The artifact-table row adds `ticket` and `parked_at`.
- **`artifacts.md`.** The `park.md` section adds `ticket`, `parked_at`, a `stage` that may be null, and "never committed; a second park exits 3". The `run.md` section lists its four fields and the log table.
- **`factory/AGENTS.md`.** Its paragraph is accurate: writers go through `update`, `load` takes no lock, retries never read as "no state yet", and `park` never touches `state.json`.

## Findings

### F1. Must fix: a `state.json` that is not UTF-8 escapes as `UnicodeDecodeError` (criterion 2)

Evidence: I wrote `b'\xff\xfe{bad'` to `state.json`. `load` raised
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`. That
is not `StateError`, and it does not name the file.

`_read` catches only `FileNotFoundError` and `OSError` around `read_text`, and
`UnicodeDecodeError` is a `ValueError`. RFC 8259 requires JSON exchanged
between systems to be UTF-8, so these bytes are malformed JSON. A caller such as
the loop, which handles `StateError` by parking, would crash instead. The safety
property still holds: the file is never read as fresh.

**Fix.** In `_read`, turn `UnicodeDecodeError` into
`StateError(f"{path}: malformed JSON: …")`, for example by adding
`except UnicodeDecodeError` before `except OSError`. Add a parametrised case or
a test that writes invalid UTF-8 and expects `StateError` naming `state.json`.
That test is red without the fix.

### F2. Should fix: the `render_run_md` docstring claims too much

The docstring says the nested block is one "which `chain.front_matter` reads back as
`cycles.<stage>`". That is false for `spec-review`, one of the two judged stages
the design names, as the builder's own test comment admits. Spec review 2, §9,
made the same claim.

**Fix.** Say that `chain.front_matter` reads back only keys that are
identifiers, so a hyphenated stage such as `spec-review` is not read. This is
harmless while nothing reads `run.md`. A future reader should not trust the
claim.

### F3. Nit: `fsync` is untested

Removing `os.fsync(handle.fileno())` leaves every test green. Criterion 5 names
fsync. A test could monkeypatch `state.os.fsync` to record its file descriptor,
and assert it is called before `os.replace`. That would make the claim mechanical
rather than by inspection. This does not block the verdict.

### F4. Note: stale temp files are never removed

A process killed between the write and the replace leaves
`state.json.tmp-<pid>` behind; my kill probe left one. It is never read, so
correctness holds. Nothing cleans it up, though, and each one has a different
pid. #210's pruning is the natural owner. Worth one line in the PR body.

### F5. Note: `TicketState` is frozen but unhashable

`hash(fresh(7))` raises `TypeError: unhashable type: 'dict'`. The generated
`__hash__` reaches the `MappingProxyType`. No criterion asks for hashing, and
nothing hashes a state today. Either say so in the docstring, or leave it for
the first caller that needs it.

## What I could not verify

- **The `fcntl` branch and its bounded wait.** Not run; this machine is Windows.
- **fsync reaching the device**, and power loss.
- **A real worker running `factory park`** through the harness. The tests and my probes call `main` in process with `chdir`.
- **Parking from a judge's snapshot, the Designer's branch name, and routing reading `park.md`.** These are out of scope by spec (#159, #222, #218).
- **The concurrent test's red under heavy load.** It depends on both subprocesses starting within the 2 s lead. On a machine slow enough to serialise them, the unlocked run could pass by luck. With the lock, the test cannot fail for that reason.

Nothing here changes which keys reach the game.
