---
ticket: 220
stage: build
radius:
  - factory/launcher.py
  - factory/launchers/__init__.py
  - factory/launchers/herdr.py
  - factory/launchers/fake.py
  - tests/test_factory/test_launcher.py
  - tests/test_factory/test_launcher_herdr.py
  - tests/test_factory/fixtures/herdr/**
  - docs/factory/design.md
  - .factory/220/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_launcher.py::test_worker_spec_carries_all_eight_credential_variables_for_every_role
  red_output_sha: see Proof below
  suite: null
docs_cleared: []
---

# Plan: the launcher, with herdr behind it

## Radius

| Path | Why |
| --- | --- |
| `factory/launcher.py` | `WorkerSpec`, `Handle`, `WorkerState`, `Launcher`, `LauncherError`, `stripped_credentials`, `worker_spec`, the credential check both launchers share |
| `factory/launchers/__init__.py` | package marker, no re-exports |
| `factory/launchers/herdr.py` | the adapter: command runner, JSON reply parsing, start/status/session_id/stop, worktree check, trust-dialog matcher, Toolhelp process-table reader |
| `factory/launchers/fake.py` | `FakeLauncher` |
| `tests/test_factory/test_launcher.py` | spec, credentials, `FakeLauncher`, worktree check |
| `tests/test_factory/test_launcher_herdr.py` | the adapter against stored replies, the real-binary guard, the process-table reader |
| `tests/test_factory/fixtures/herdr/**` | stored herdr replies and screens, each recorded as captured or constructed |
| `docs/factory/design.md` | §8 and §12 |
| `.factory/220/**` | the chain |

**Not in the radius:** `pyproject.toml` (the packaging line goes to the maintainer, see the spec), `factory/merge.py` and its protected set, `CONTEXT.md`.

## Order of work

1. Write the red tests. Run them before any source exists and record the failure lines.
2. `factory/launcher.py`, then `fake.py`, then `herdr.py`. Run green.
3. `design.md` §8 and §12.
4. Full suite, ruff check, ruff format, pyright on the changed Python files.
5. Commit, then record the proof.

## Design of the code

- `Launcher.start` and the credential check live in `launcher.check_credentials(spec, common_dir)`. Both launchers call it first, so it runs before any record or herdr command.
- The adapter takes `common_dir`, an injected `run` (argument list in, `CommandResult` out), an injected `read_process_table`, `environ`, `sleep`, `monotonic` and a `Timeouts` record. The default `run` is `subprocess.run` with an argument list and no shell. It lives in the module as `default_runner`, which the test guard replaces so that a test reaching it fails.
- A herdr reply is JSON. Exit 0 is read from stdout and must carry `result`. A non-zero exit is read from stderr (stdout as fallback) and must carry `error.code`. Anything else is a `LauncherError`.
- Timeouts (herdr timings, not Expectations): `agent start` 60 s, the post-trust `agent wait` 30 s, `agent prompt` 60 s, `stop`'s wait 30 s polled each 0.25 s.

## The four notes from the passing spec review, settled

1. **Back-pointer compare (criterion 13)** compares resolved `Path` objects, never strings. Git writes `C:/Users/.../.git`. A test writes the back-pointer with `as_posix()` and expects the trust answer to be sent. A mismatched one is also tested.
2. **The per-process record (criterion 8)** is `HerdrLauncher._started: dict[str, Handle]`, keyed by worker name and filled by every `start` that returns a Handle. `start` checks it before `agent get`. A second `start` on the same launcher returns the recorded Handle (prompt seen to start). A fresh launcher has an empty record, so `agent get` finds the name and returns a Handle marked not seen to start. `FakeLauncher` keeps the same kind of record.
3. **Could not verify:** whether the pane id, and not only the name, works for `agent read` and `send-keys` while startup is blocked (`agent_not_ready`). If it does not, the read returns `agent_not_found`, `start` raises with the Handle and fails closed.
4. **The live trust dialog** is committed as `tests/test_factory/fixtures/herdr/trust-dialog-live.txt`, recorded as captured live from herdr 0.9.5 (2026-10-22). Criterion 12 is tested against it. It differs from the spec's wording in one respect: the options are **not numbered**. The live screen reads `❯ No, exit` then `Yes, I trust this folder`. The matcher therefore treats the numbers as optional: with none, "No, exit" immediately followed (whitespace only) by "Yes" is accepted; with numbers, the second must be n+1; a number on one option only is refused. Nothing may sit between the two options.

## Other choices

- `pane split` is issued without a target pane. Which pane herdr divides when none is given is not verified (see *Could not verify* in the proof).
- Stored replies: error replies and the trust screen are captured; replies from mutating commands are constructed from the bundled schema. The test module has one table saying which, and a test fails if a file is missing from it.
- After `stop` returns, the adapter remembers the pane id and `status` answers `gone` for it.
