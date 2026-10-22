---
ticket: 216
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 533ba4210d7ad2aaee01cdfc495177395cf9c029
---

# Review: the hook runs the main checkout's gate code

**Verdict: `changes-requested`.** All eight criteria are met, and the red proof
reproduces exactly. One finding (F1) is a real way the new `_session_root`
makes a gate decision worse than before, and the fix is a few lines inside the
radius. F2 and F3 are minor. F4 is a note.

## What I ran

All runs used `C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`, from the
worktree root.

- **`pytest -q -p no:cacheprovider`:** `1203 passed, 3 skipped, 25 deselected`.
  0 failed, 0 errors, 0 xfailed. The 3 skips are the movement-lab Expectations.
- **`ruff check` and `ruff format --check`** on `factory/cli.py`,
  `tests/test_factory/test_cli.py` and `tests/test_factory/test_hook_wiring.py`:
  clean.
- **`pyright`** on the same three files: 0 errors. The worktree has no
  `.venv`, so a bare `pyright` reports "Import pytest could not be resolved".
  That is an environment artefact. With `--pythonpath` set to the venv
  interpreter, the result is clean.
- **Red proof.** I ran
  `git checkout 9654223 -- .claude/hooks/factory-hook.sh factory/cli.py`, kept
  the tests, and ran `test_cli.py` and `test_hook_wiring.py`. The result was
  `3 failed, 38 passed`. The three failures and their reasons:
  - `test_a_factory_package_in_the_session_cwd_cannot_answer_for_the_gate`:
    `the session's own factory package answered`, because
    `'SHADOW-FACTORY-ANSWERED' not in 'SHADOW-FACTORY-ANSWERED\n'`. This
    matches the plan.
  - `test_the_pre_tool_use_hook_takes_the_session_from_the_event_s_cwd`:
    `the hook made no decision`.
  - `test_the_stop_hook_takes_the_session_from_the_event_s_cwd`:
    `the hook made no decision`.

  I restored with `git checkout HEAD -- <both>`. `git status` was clean
  afterwards.
- **Mutations of the new guards**, each one restored the same way:
  - With the `isatty` guard replaced by `if False:`, the terminal test fails
    with "the hook read from a terminal and would hang". The test does pin the
    guard. It passed before the change only because session-start read nothing
    then.
  - With the `is_dir()` check dropped, the missing-directory test fails with
    "the hook made no decision".
- **Isolated-mode check.** I ran the primary venv's python with `-I` from a
  temporary directory that holds a shadow `factory/`. `factory.__file__`
  resolves to `C:\Users\Nassim\code\Legends\factory\__init__.py`, with
  `sys.flags.safe_path=True`. Without `-I`, the shadow is imported.

  The primary's editable install is the setuptools finder kind
  (`__editable___legends_factory_0_1_0_finder.py`, with
  `MAPPING = {'factory': 'C:\\Users\\Nassim\\code\\Legends\\factory'}`). It is
  appended to `sys.meta_path`. That is why the current directory, which sits
  ahead of it on `sys.path`, used to win.

## Criteria

| # | Criterion (abridged) | Met | Evidence |
| --- | --- | --- | --- |
| 1 | Run as `factory-hook.sh` runs it, from a directory with a shadow `factory`, session-start prints `factory gates: LIVE` and never the sentinel | Met | The shadow test passes on HEAD. It fails on the reverted script with the sentinel in stdout. It asserts the heartbeat as well as the sentinel's absence, and fails rather than skips on `unreachable`. |
| 2 | `factory` resolves through installed packages, with the cwd off the import path | Met | The script line is `exec "$python" -I -m factory hook "$event"`, with a comment saying why. The probe above shows `-I` resolving to the install, and plain `-m` to the shadow. See F3 for what that now depends on. |
| 3 | Every event takes its session root from the event `cwd` when it names an existing directory, and from the process cwd otherwise. Tests for pre-tool-use, for stop, and for a missing directory | Met as written | `_session_root`, the three new tests, and the mutation above. **F1 is a gap in the rule**, not in the tests. |
| 4 | A terminal on stdin reads nothing, so running `factory-hook.sh` by hand does not hang | Met for a console terminal | `_read_stdin` checks `sys.stdin is None or sys.stdin.isatty()`. `_Terminal` pins it. **F2:** Git Bash's mintty is not a console to `python.exe`. |
| 5 | A pre-tool-use event whose `cwd` is a linked ticket worktree is judged with that worktree as the session, from an unrelated process cwd | Met | `test_the_pre_tool_use_hook_takes_the_session_from_the_event_s_cwd` is red before the change and green after. |
| 6 | No interpreter: the hook prints its unreachable message and exits 0, tested from a copied script with no venv | Met | `test_a_hook_with_no_interpreter_says_so_and_exits_zero`. The copy sits in a `tmp_path` with no `.git`, so `main_repo` cannot reach the primary's venv. It passes before and after the change, as a regression guard should. |
| 7 | Every existing test in `tests/test_factory` passes unmodified | Met | `git diff 9654223..HEAD -- tests` has no removed lines: 213 insertions only, plus `from typing import Any`. The full suite is green. |
| 8 | `factory/AGENTS.md` says which code a hook runs and why the cwd is kept off the path. The console-script sentence is corrected | Met | "How it runs" now says the hooks run `python -I -m factory` by interpreter path, and why. The new "Which code a hook runs" paragraph covers it. The wording in it overclaims; see F3. |

The radius is respected. The diff touches only the five listed paths and
`.factory/216/**`. `factory/hooks.py` and `.claude/settings.json` are unchanged.
`.claude/**` makes this a human merge, as the plan says.

## Findings

### F1. An event `cwd` inside a worktree, rather than at its root, turns the Stop gate off (should fix)

`_session_root` returns the event's `cwd` verbatim. Only `decide_write` copes
with a subdirectory, because it calls `governing(session)`, which walks up to
the nearest `.git`. Everything else on the hook path treats `repo_root` as a
worktree root:

- `current_branch` and `git_dir` look at `repo_root / ".git"`.
- `ticket_worktrees` returns `()` when `git_dir` is `None`.
- `session_report` reads `repo_root/.factory/<n>`.

So when the event's `cwd` is a subdirectory such as `<worktree>/botting` and
the process cwd is the worktree root, the change makes two decisions worse.

**Evidence.** I used the repo's own `_primary` and `_linked` fixtures, a
ticket-5 worktree whose plan has `suite: null`, `_source_changed` forced to
true, and the process cwd at the worktree root. The probe script is
`probe_subdir2.py` in the review session's scratchpad.

| Event | stdin `{}` (old behaviour) | stdin `{"cwd": "<wt>/botting"}` |
| --- | --- | --- |
| `stop` | `{"decision": "block", "reason": "Source changed on ticket 5 but plan.md records no proof..."}` | no output, so the turn is allowed |
| `session-start` | "You are on a factory ticket branch: ticket 5..." | "Not in a ticket worktree..." |

`pre-tool-use` is unaffected, because of `governing`.

Whether the harness ever sends a subdirectory `cwd` while running the hook at
the root cannot be checked offline. The spec says so. But the change's own
stated reason is the day the two differ (#220, a launcher running hooks from
elsewhere). In that world an agent that has `cd`'d into `botting/` is the
ordinary case, and the proof gate is the one that goes quiet. That is the #206
failure class again.

**Fix.** Inside the radius, in `factory/cli.py`: resolve the chosen directory
to the worktree that governs it before returning it. For example:

```python
found = governing(candidate)
return found.root if found is not None else candidate
```

This uses `factory.hooks.governing`, and `hooks.py` itself is not edited. Do it
for the event `cwd` at least. Applying it to the `Path.cwd()` fallback as well
would also close the same pre-existing hole for a process started in a
subdirectory. If you do, say in the PR body that this changes behaviour.

Add a test: process cwd unrelated or at the root, event `cwd` set to
`<linked>/botting`, and `stop` blocks. It is red on HEAD; the probe above shows
that.

### F2. The `isatty` guard does not cover Git Bash's mintty (minor)

A native `python.exe` under mintty sees a pipe, not a console. This is why
`winpty python` exists. `isatty()` is then `False`, and `sys.stdin.read()`
waits for EOF. Before the change, session-start read nothing, so the by-hand
check could not hang.

**Evidence.** I could not test inside mintty. I reproduced the pipe case by
feeding the hook a stdin pipe held open for 6 s, timing when python exits:

```
(sleep 6) | ( python    -m factory hook session-start ... )   # branch code:  6s
(sleep 6) | ( python -I -m factory hook session-start ... )   # primary code: 1s
```

Agents are not affected. The Claude Code Bash tool's stdin is `/dev/null`: from
it, `fd/0 -> /dev/null`, and the branch's hook returned in about 1 s. A real
harness event is never a terminal either: Claude Code pipes the JSON and closes
it. `sys.stdin is None` does not arise on this path. It happens under
`pythonw.exe` or a process started with no std handles, and the hook execs
`python.exe` from bash with bash's stdin. The check is harmless defence: before
it, a `None` stdin would have raised an uncaught `AttributeError`.

**Fix.** In `factory-hook.sh`, decide in bash, which does recognise its own pty
as a terminal under mintty:

```bash
if [[ -t 0 ]]; then exec "$python" -I -m factory hook "$event" </dev/null; fi
```

Keep the Python guard for consoles. Alternatively, name the mintty case in the
PR body's Could not verify.

### F3. The hook now depends on the editable install, and the docs say `-I` guarantees more than it does (minor, docs)

`-I` guarantees that the cwd is not consulted. It does not decide which code
runs: the editable install's `MAPPING` does. That has two consequences, and the
diff states neither.

- **A venv without `pip install -e . --no-deps` now fails differently.** Before
  the change, a session in the primary checkout ran fine without the install,
  because the cwd supplied `factory`. Now:

  ```
  python.exe -I -m factory hook session-start
  -> "No module named factory", rc=1
  ```

  I checked this with the base 3.14 interpreter. Without `-I`, from the same
  directory, the hook answers with rc=0. Exit 1 is non-blocking, so the gates
  are silently off. The #199 "unreachable" message does not fire, because an
  interpreter *was* found. Only the missing heartbeat gives it away. CI
  installs editable (`merge-policy.yml:87`), and `docs/SETUP.md` documents the
  step, so this is a doc gap rather than a break.
- **An install run from a worktree repoints every session at that worktree.** A
  worktree has no venv, so someone running `pip install -e .` inside it uses the
  main venv's python. That rewrites `MAPPING` to point at the worktree, and
  every session's gate becomes that worktree's code. `factory/AGENTS.md` says
  "It never runs a worktree's own copy ... `-I` (isolated mode) is what
  guarantees this", and that is not quite true.

**Fix.** Two sentences in `factory/AGENTS.md`, "Which code a hook runs":

1. The hook needs the editable install, made **from the main checkout**.
2. Without it, the hook exits 1 with "No module named factory", and the
   heartbeat is missing.

Optionally, the script can turn that case into the `unreachable` message.
Since `exec` cannot see python's failure, that means running python without
`exec` and checking for the import error. That costs nothing on the success
path.

### F4. What the shadow test proves (note, no change needed)

Run in a worktree with no `.venv`, as here, `_hook_python` and the script both
pick the main checkout's interpreter. The script under test is the
**branch's**, read via `ROOT`. The Python behind it is the **primary
checkout's**. The test therefore proves the branch's `-I` and nothing in the
branch's `cli.py`. The in-process tests cover `cli.py`. The spec and
`factory/AGENTS.md` both say this, correctly.

Two consequences follow, and they are worth a line in the PR body:

- **It can fail for reasons unrelated to the branch.** It passes only if the
  primary's checked-out `factory` prints `factory gates: LIVE` for a directory
  outside any repository. `dev` does, since #202. A primary checked out on an
  older commit, or a future change to the heartbeat on `dev`, makes it fail.
- **It cannot detect a primary that is behind.** That is the spec's first
  Could not verify, and it stands.

In CI, or in the primary checkout, `ROOT/.venv` exists, and the install maps to
`ROOT`. The test then exercises the same tree it runs from. `_hook_python`
checks `is_file()` where the script checks `-x`. On Windows they are
equivalent. On POSIX a non-executable venv python would be skipped by the
script and found by the test, which would then fail on `unreachable` and not
pass vacuously. That is the safe direction.

## What I could not verify

- **How Claude Code actually runs a hook.** That is: what process cwd it
  starts the hook in, whether the event's `cwd` follows a Bash `cd`, and
  whether the two ever differ. F1 matters only if they can differ with a
  subdirectory `cwd`.
- **That the harness closes stdin for SessionStart and Stop.** Every event now
  reads stdin to EOF. Claude Code documents piping JSON to every hook. If it
  ever left stdin open without writing, session-start and stop would block
  until the hook timeout. Before the change they read nothing.
- **Behaviour inside mintty itself (F2).** I reproduced only the open-pipe
  mechanism.
- **The plan's `red_output_sha: 799fc0138c55`.** It names no hashing procedure
  I could reproduce. I re-ran the red tests instead, and the failure text
  matches the plan's excerpt.
- **Anything about keys reaching the game.** Not applicable: the change
  touches only factory tooling.
