---
ticket: 220
stage: design
method: suite
criteria:
  - factory/launcher.py defines a frozen WorkerSpec with exactly the fields name, cwd, env, model, prompt and resume, a frozen Handle carrying the worker's name, its pane id, its role and whether its prompt was seen to start, a WorkerState enum whose members are exactly working, finished, blocked and gone, and a Launcher Protocol with exactly start, status, session_id and stop
  - WorkerSpec refuses a name that does not match herdr's [a-z][a-z0-9_-]{0,31}, refuses a non-null resume unless env FACTORY_ROLE is designer, and keeps its own read-only copy of env, so mutating the mapping passed in afterwards changes nothing the spec carries
  - stripped_credentials(common_dir) returns exactly eight variables, GH_TOKEN as the non-empty sentinel factory-worker-has-no-credentials, GH_CONFIG_DIR as a directory under the git common dir, GITHUB_TOKEN as the empty string, GIT_ASKPASS as the empty string, GIT_TERMINAL_PROMPT as 0, GIT_CONFIG_COUNT as 1, GIT_CONFIG_KEY_0 as credential.helper and GIT_CONFIG_VALUE_0 as the empty string, and creates the GH_CONFIG_DIR directory when it is absent
  - stripped_credentials raises, and returns nothing, when the GH_CONFIG_DIR directory already exists and is not empty
  - worker_spec, the one function the loop will build a WorkerSpec with, gives every spec FACTORY_ROLE, FACTORY_STAGE and FACTORY_TICKET plus all eight variables stripped_credentials returns, with those values, for each of the roles designer, spec-reviewer, planner, builder and reviewer, and its test goes red when any one of the eight is dropped
  - every launcher is constructed with the git common dir, and its start refuses a spec that lacks any of the eight credential variables or carries one with a value other than the one stripped_credentials gives for that common dir, raising an error that names the variable before any worker is recorded or any herdr command is issued, on FakeLauncher and on the herdr adapter
  - FakeLauncher records each started spec in order, answers status with each name's scripted state sequence one call at a time, repeating the last state, and answers session_id with a scripted id or None
  - start is idempotent by name, on FakeLauncher and on the herdr adapter, so a second start on the same launcher with a name already started returns a Handle equal to the first and starts no second worker, and a herdr adapter whose agent get finds the name issues no pane split, agent start, agent prompt or send-keys and returns a Handle with that agent's pane id whose prompt is marked as not seen to start
  - the herdr adapter's status calls agent get with the Handle's pane id, never its name, and maps agent_status working and unknown to working, idle and done to finished, blocked to blocked, and an agent_not_found error to gone, except that for a Handle whose prompt was not seen to start, idle and done map to blocked and never to finished, each tested against a recorded agent get reply
  - any herdr error code not named in these criteria, a reply that is not JSON, and an agent_status outside herdr's five each raise a launcher error, and none is ever mapped to a WorkerState
  - the herdr adapter's start for a new name issues, in this order and each as an argument list never passed through a shell, one pane split with --no-focus, --cwd set to the spec's cwd and one --env KEY=VALUE per env entry including the empty-valued ones, then agent start with the name, --kind claude, --pane set to the pane_id the split returned, a --timeout, and after -- the arguments --model with the spec's model plus --resume with its id only when resume is set, then agent prompt with the split's pane id and the spec's prompt followed by --wait --until working --until blocked and a --timeout, with no -- before the prompt, and every agent command after agent start targets that pane id
  - when agent start reports agent_not_ready and agent get reports blocked, the adapter reads the screen with agent read --source recent-unwrapped, collapses every run of whitespace to one space, and sends the keys down then enter exactly once only if that text contains Is this a project you created or one you trust? followed by an option numbered n reading No, exit and then, with only whitespace between, an option numbered n+1 whose text starts with Yes, and the spec's cwd is a linked worktree of the launcher's repository, and it then waits with agent wait and a --timeout and sends the prompt only if the settled state is idle or done
  - the spec's cwd counts as a linked worktree of the repository only when cwd/.git is a file whose gitdir, resolved against cwd when relative, is a direct child of the resolved git common dir's worktrees directory, and that child's own gitdir file names the resolved cwd/.git, and each of a relative gitdir, a gitdir outside worktrees and a missing or mismatched back-pointer is tested
  - every error start raises after a successful pane split carries the Handle and sends no keys beyond the single trust answer and no prompt that was not already sent, tested for the trust dialog outside a linked worktree, the trust dialog in any other layout, any other blocked screen, a blocked state after the trust answer, agent_not_found after the trust answer, an agent start that times out or returns any code other than agent_not_ready, a state other than blocked after agent_not_ready, and an agent prompt that returns agent_prompt_stalled, timeout or any other error
  - the herdr adapter's session_id returns agent_session.value from the agent list entry whose pane_id is the Handle's when agent_session.kind is id, and None when no entry has that pane_id, when agent_session is null, and when kind is path
  - stop raises, issuing no herdr command and closing nothing, for a Handle whose role is designer, on FakeLauncher and on the herdr adapter, and for a Handle whose pane id is the HERDR_PANE_ID of the launcher's own environment, on the herdr adapter
  - the herdr adapter's stop closes only the Handle's own pane id, never a pane resolved from the agent's name
  - the herdr adapter's stop treats pane_not_found from pane process-info as already stopped and returns normally without closing anything, so a second stop on the same Handle also returns normally
  - otherwise the herdr adapter's stop raises before closing anything unless herdr reports a shell_pid and that pid is present in the pre-close process-table snapshot, then records the shell pid, the foreground pids and all of their descendants in that snapshot, closes the pane, returns only once none of those pids appears in a fresh snapshot, and raises rather than returning normally when any is still present after the stop timeout, with a test whose reader returns an empty table
  - after stop returns for a Handle whose role is not designer, status for that Handle is gone, on FakeLauncher and on the herdr adapter
  - the default process-table reader, called on Windows, lists the running test process together with its parent pid, and on any other platform raises NotImplementedError when called, and importing it never raises on any platform
  - the herdr adapter's tests drive it only through herdr replies stored as files under tests/test_factory/fixtures/herdr/, the test module records for each file whether it was captured from herdr 0.9.5 or constructed from that version's bundled API schema, captured files are trimmed to the fields the adapter reads, and a guard fails any test that reaches the real herdr binary
  - docs/factory/design.md section 8 describes the credential set, the trust-dialog handling and that pane split takes repeated --env, and section 12 no longer lists the five launcher questions as unverified and lists instead what this ticket could not verify
  - the only files changed are factory/launcher.py, factory/launchers/__init__.py, factory/launchers/herdr.py, factory/launchers/fake.py, new test modules and fixtures under tests/test_factory/, docs/factory/design.md and .factory/220/, so factory/merge.py, its protected set and pyproject.toml are unchanged
  - pytest from the worktree root reports 0 failed, 0 errors, 0 xfailed, and ruff check, ruff format and pyright at standard are clean on every new file
specified_by: claude
specified_at: 2026-10-22
revised_at: 2026-10-22
revised_after: spec-review.md (changes-requested, 7 findings)
---

# Spec: the launcher, with herdr behind it

## Source

- Issue #220, its body and the comment carrying #215's results.
- #215's comments: the full live findings of 2026-10-22, in herdr 0.9.5.
- `docs/factory/design.md` §4 rules 1 and 6, §5 (`launcher.py`), §8, §12.
- herdr 0.9.5's own CLI help and bundled API schema (`herdr api schema --json`,
  protocol 22). The help is the authority on syntax.
- `spec-review.md` (changes-requested, seven findings), and the coordinator's
  choices where the review left one. This revision settles every finding; the
  table at the end maps each to the criteria it changed.

Where #215 and design §8 disagree, this spec follows #215, as the issue body
says. They disagree in one place: §11/§12's single-variable fallback for
`pane split --env` is unnecessary, because `--env` repeats.

The spec departs from the **issue body** in two places, each for the issue's
own stated goal (see *Decisions*): `GH_TOKEN` is a sentinel rather than empty,
and `agent prompt` waits for the turn to start rather than not waiting at all.

## What #215 settled, and what follows

| Finding | Consequence here |
| --- | --- |
| `pane split --env` repeats, and the env reaches every hook | The adapter passes every variable through the CLI, one `--env` each (criterion 11). The socket API's map is not needed. |
| A fresh folder raises the trust dialog; default "No, exit"; it blocks startup | Recognised by its text and layout and answered, only for linked worktrees of this repository (criteria 12, 13). |
| Any other startup dialog (the MCP approval) also shows as `blocked` | Never answered. Start fails, carrying the Handle (criterion 14). |
| Workers inherit auto mode | Credential stripping is not optional (criteria 3 to 6). |
| `agent_session.value` carries the session id | `session_id` reads it (criterion 15). |
| No `unknown` state was seen | Mapped to working anyway, per the issue and herdr's docs (criterion 9). |

## Facts read off herdr 0.9.5 offline (2026-10-22)

Read-only calls only. No pane was created and no agent started.

- `herdr agent get zz-no-such-agent` exits 1 with
  `{"error":{"code":"agent_not_found",...},"id":"cli:agent:get"}`. The reviewer
  confirmed the same code for a closed pane id (`agent get w99:p999`). That
  code is what `gone` means.
- `pane process-info` on a missing pane returns a different code,
  `pane_not_found` (reviewer's probe). Criterion 18 gives it a meaning.
- `agent list` returns `result.agents`, each an `AgentInfo` with `pane_id`,
  `agent_status` and `agent_session` (`{agent, kind, source, value}`, kind `id`
  or `path`, or null). Named agents carry `name`.
- `pane process-info` returns `result.process_info` with `shell_pid` and
  `foreground_processes[].pid`. It does not list background descendants, which
  is why criterion 19 walks a process table. The reviewer confirmed that these
  are Windows pids and that a stdlib Toolhelp reader sees them.
- `agent start` returns `agent_not_ready` at once when startup is blocked, and
  keeps the agent addressable for `agent read` and `agent send-keys`.
- `agent prompt --wait` with `--until working --until blocked` returns once
  activity is seen, not at the end of the turn. It returns
  `agent_prompt_stalled` if no activity appears within five seconds.
  `herdr agent prompt x -- "-x"` exits 2, so no `--` precedes the prompt.
- CLI server errors are JSON on stderr with exit 1; syntax errors exit 2.

## Decisions I made

- **`GH_TOKEN` is the sentinel `factory-worker-has-no-credentials`, not empty**
  (review finding 1). The issue says `GH_TOKEN=`. The reviewer showed that
  with an empty `GH_TOKEN` and an empty `GH_CONFIG_DIR`, gh 2.98.0 still reads
  the maintainer's token from the Windows keyring. So the issue's literal value
  does not meet the issue's own goal ("cannot … call GitHub by mistake"). A
  non-empty `GH_TOKEN` wins over the keyring and over `GITHUB_TOKEN`, GitHub
  rejects it, and `gh auth login` refuses while it is set.
- **Three more variables** (review finding 1). `GITHUB_TOKEN=` stops an
  inherited token reaching tools other than gh. `GIT_ASKPASS=` and
  `GIT_TERMINAL_PROMPT=0` close the askpass route the reviewer showed around
  the `credential.helper` reset, and stop `git push` waiting on the pane's
  console for a username. That makes eight variables.
- **The credential check lives in `start`, not in `WorkerSpec`.** The issue's
  `WorkerSpec` is a plain record. Every `Launcher.start` refuses a spec without
  the eight variables (criterion 6), and `worker_spec` always adds them
  (criterion 5). A spec built by hand therefore cannot reach a worker. The
  fake's assertion is the same check, so it is testable. Each launcher takes
  the git common dir, because comparing `GH_CONFIG_DIR` needs it.
- **`GH_CONFIG_DIR` is `<git-common-dir>/factory/gh-config-empty/`**, beside the
  loop state design §4 rule 5 puts under `<git-common-dir>/factory/`. A
  non-empty directory raises (criterion 4). Otherwise a worker that wrote gh
  config there would leave it for every later worker.
- **The prompt waits for the turn to start** (review finding 4). The issue's
  "without `--wait`" is about not blocking for the whole turn. An unwaited
  prompt lets the first `status` read `idle` before Claude picks it up, and the
  loop would judge an empty turn. `--until working --until blocked` returns at
  the first activity, so `start` still does not block for the turn. A Handle
  records whether its prompt was seen to start. `status` never reports
  finished for one that was not (criterion 9).
- **A replayed start never re-sends the prompt.** If the loop crashed between
  `agent start` and a seen prompt, the replay finds the agent and returns a
  Handle marked "not seen to start". Its idle reads as `blocked`, so the
  attempt fails and is stopped rather than judged as an empty turn. A prompt
  delivered twice would be worse. A crash replay costs one attempt.
- **A pane split that crashed before `agent start` is leaked**, not adopted.
  The replay finds no agent by that name and splits a new pane. Every failure
  *after* a successful split, in the same process, carries the Handle
  (criterion 14), so the loop can stop it.
- **Every wait is bounded** (review finding 2): `agent start --timeout`, the
  `agent wait` after the trust answer, `agent prompt --timeout`, and `stop`'s
  wait. The plan picks the defaults. They are herdr timings, not Expectations
  about the game.
- **The trust dialog is answered in one layout only** (review finding 3): the
  question, then "No, exit" as option n, then, with only whitespace between,
  option n+1 starting "Yes". That is the layout in which `down enter` selects
  Yes. Nothing may sit between the two options, so a cursor marker on the Yes
  option disqualifies the screen. Any other layout gets no keys, and start
  raises with the Handle. The text is read `recent-unwrapped` and
  whitespace-normalised, so a narrow pane wrapping the question cannot hide it.
- **The answer is `down enter`, once**, from #220's comment. If it is wrong, the
  worker exits (`agent_not_found`) or stays blocked, start raises with the
  Handle, and the attempt fails. It never answers twice.
- **Only linked worktrees of this repository** get the answer, identified by
  git's own pairing (criterion 13): `.git` is a file whose `gitdir`, resolved,
  is `<common>/worktrees/<id>`, and `<common>/worktrees/<id>/gitdir` points
  back at that `.git`. The maintainer's own herdr worktrees qualify, which is
  harmless: they are this repository.
- **`status`, `session_id` and every agent command after `agent start` target
  the pane id**, not the name. A name follows whichever agent holds it. The
  pane id is what the loop created. After a close, `agent get` on it returns
  `agent_not_found`, so `status` reads `gone` (criterion 20).
- **`stop` raises for a designer Handle and for the launcher's own pane**
  (review finding 6). The loop never legitimately asks for either, and a silent
  return would break the protocol's promise that `stop` returns once the tree
  is gone. The own pane is `HERDR_PANE_ID`, the pane the loop or the
  orchestrator is running in: "you are talking to it".
- **`pane_not_found` on `stop` means already stopped** (review finding 5). A
  replay after a crash, or a pane the maintainer closed by hand, then returns
  normally and idempotently, instead of raising forever. Whether its processes
  outlived the pane is under *Could not verify*.
- **`stop` cannot pass vacuously** (review finding 5). It requires herdr's
  `shell_pid` and requires that pid in its own pre-close snapshot, or it raises.
  A broken reader that returns an empty table therefore raises.
- **`stop` waits on a process table, not on herdr.** A pid counts as alive while
  it appears in a fresh snapshot. A reused pid, or a reused parent pid linking
  an unrelated older process into the tree, errs towards waiting: the wait
  times out and `stop` raises. That can fail an attempt spuriously, which is
  the safe direction. The reader is injected. The default uses Windows'
  Toolhelp snapshot through `ctypes`, the standard library, because `psutil`
  is not a declared dependency. On another platform it raises when called, so
  CI on Linux still imports the module.
- **`FakeLauncher` lives in `factory/launchers/fake.py`**, not under `tests/`.
  It implements the protocol, it is held to the package's typing gate, and the
  dry run (#223) may need it outside the suite.
- **Roles are strings here.** `roles.py` arrives with #218. The test covers the
  five dispatchable roles named in design §8, and not the orchestrator, which is
  never launched.
- **Not adopted: comparing an idempotent hit's `cwd` with `spec.cwd`** (review
  note). herdr reports `cwd` in more than one form (the reviewer's capture ends
  `process-info`'s cwd with a backslash), and a false mismatch would fail a
  legitimate replay. Names are loop-generated, so a collision means a loop bug.
- **Prompts stay short** (review note). The prompt travels as one argument, and
  a Windows command line is capped at 32,767 characters. Role prompts point at
  files. The loop owns their content.
- **`CONTEXT.md` gains nothing.** "Worker" and "launcher" are not in the
  glossary. Adding them is outside this ticket's files, and noted in the PR.

## `merge.py`, the protected set, and packaging

`test_every_module_the_console_script_imports_is_protected` walks the static
imports of `factory.__main__` and `factory.cli`. Nothing in that closure will
import `factory.launcher` or `factory.launchers`, so **the test is unaffected
and `merge.py` is not edited** (criterion 24). This was checked by reading the
closure at `9654223`: `cli`, `chain`, `routing`, `hooks`, `models`, `merge`,
`exit_codes`, `__init__` and `__main__`. The reviewer confirmed it.

Until #217 replaces the list with `factory/**`, the launcher's modules are not
protected. A later `type:chore` PR touching only them could merge itself. They
feed nothing in the merge verdict, so that is acceptable. This ticket is
`type:build` and never auto-merges.

### Maintainer action: packaging

`pyproject.toml` packages `["factory"]` only. The editable install maps the
package directory, so `factory.launchers` imports, and CI installs editable
(`merge-policy.yml:87`). A non-editable build omits the subpackage: the
reviewer built a wheel from a copy and it held no `factory/launchers/`.
`pyproject.toml` is a hard-stop path for every agent, so this ticket does not
edit it. The PR hands the maintainer the exact one-line edit, under `[tool.setuptools]`:

```toml
packages = ["factory", "factory.launchers"]
```

replacing `packages = ["factory"]`.

## Verification method: suite

Every criterion is settled by a test or by a check on the diff. The adapter
takes an injected command runner and process-table reader, and its tests feed
it recorded replies. Replies from read-only commands can be captured from the
live herdr, trimmed to the fields the adapter reads so that no session id,
path or command line of the maintainer's is committed. Replies from mutating
commands (`pane split`, `agent start`, `agent prompt`, `agent send-keys`,
`agent wait`, `pane close`) are constructed from the bundled schema, since
creating panes is out of bounds. The test module says which is which
(criterion 22).

## Could not verify (for the PR)

- The adapter against a live herdr. #215 is the live evidence.
- **Whether herdr passes an empty `--env` value through.** #215 tested only
  non-empty values. If herdr drops `GIT_CONFIG_VALUE_0=`, `GIT_CONFIG_COUNT=1`
  arrives without it and every git command in the worker fails ("missing
  config value GIT_CONFIG_VALUE_0"). That fails closed, but it would stop every
  Builder. A dropped `GITHUB_TOKEN=` or `GIT_ASKPASS=` would let an inherited
  value through. `GH_TOKEN` is non-empty, so it is unaffected.
- The trust dialog's option order, and whether `down` wraps. If the live layout
  differs from the one criterion 12 accepts, every first dispatch into a fresh
  worktree fails closed until the layout is recorded.
- That closing a herdr pane on Windows ends background descendants. `stop`
  waits for the descendants it can see and raises if they outlive the timeout.
- **Orphaned background processes.** A parent-pid walk cannot find a process
  whose parent exited before the snapshot, such as `nohup … &` from a Bash call
  that already returned. That is close to re-check X3's case. The issue's
  "returns only once the process tree is gone" is true only of the tree the
  snapshot shows. The same holds for a pane already gone at `stop`.
- Whether Git Credential Manager is reachable by a route other than
  `credential.helper` and askpass. The reviewer showed the reset clears
  system- and global-scope helpers with marker helpers, not with the real
  `manager` against github.com.

## Not in scope

- The loop (#159), which calls the launcher, persists Handles, and fails
  attempts. Timeouts on a worker's turn are the loop's.
- `roles.py` and the role table (#218).
- `proof.py`'s use of the same environment (design §8), which arrives with it.
- Protecting `factory/**` (#217).

## Review findings, and where each is settled

| Finding | Settled in |
| --- | --- |
| 1. Credentials | criteria 3, 5, 6; *Decisions*; *Could not verify* |
| 2. Leaked panes | criteria 11, 12, 14; *Decisions* (bounded waits) |
| 3. Trust-dialog layout and worktree check | criteria 12, 13, 14 |
| 4. Prompt race | criteria 1, 8, 9, 11 |
| 5. `stop` vacuous pass, gone pane, orphans | criteria 18, 19; *Could not verify* |
| 6. `status` target; `stop` on designer and own pane | criteria 9, 16 |
| 7. Packaging | *Maintainer action: packaging*; criterion 24 |
