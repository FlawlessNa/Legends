---
ticket: 220
stage: design
method: suite
criteria:
  - factory/launcher.py defines a frozen WorkerSpec with exactly the fields name, cwd, env, model, prompt and resume, a frozen Handle carrying the worker's name, its pane id and its role, a WorkerState enum whose members are exactly working, finished, blocked and gone, and a Launcher Protocol with exactly start, status, session_id and stop
  - WorkerSpec refuses a name that does not match herdr's [a-z][a-z0-9_-]{0,31}, refuses a non-null resume unless env FACTORY_ROLE is designer, and keeps its own read-only copy of env, so mutating the mapping passed in afterwards changes nothing the spec carries
  - stripped_credentials(common_dir) returns exactly five variables, GH_TOKEN as the empty string, GH_CONFIG_DIR as a directory under the git common dir, GIT_CONFIG_COUNT as 1, GIT_CONFIG_KEY_0 as credential.helper and GIT_CONFIG_VALUE_0 as the empty string, and creates the GH_CONFIG_DIR directory when it is absent
  - stripped_credentials raises, and returns nothing, when the GH_CONFIG_DIR directory already exists and is not empty
  - worker_spec, the one function the loop will build a WorkerSpec with, gives every spec FACTORY_ROLE, FACTORY_STAGE and FACTORY_TICKET plus all five variables stripped_credentials returns, with those values, for each of the roles designer, spec-reviewer, planner, builder and reviewer, and its test goes red when any one of the five is dropped
  - start refuses a spec that lacks any of the five credential variables or carries one with a different value, raising an error that names the variable before any worker is recorded or any herdr command is issued, on FakeLauncher and on the herdr adapter
  - FakeLauncher records each started spec in order, answers status with each name's scripted state sequence one call at a time, repeating the last state, and answers session_id with a scripted id or None
  - start is idempotent by name, so a second start with a name already started returns a Handle equal to the first and starts no second worker, on FakeLauncher and on the herdr adapter, where an agent get that finds the name means no pane split, agent start or agent prompt is issued
  - the herdr adapter's status maps agent_status working and unknown to working, idle and done to finished, blocked to blocked, and an agent_not_found error to gone, each tested against a recorded agent get reply
  - any other herdr error code, a reply that is not JSON, and an agent_status outside herdr's five each raise a launcher error, and none is ever mapped to a WorkerState
  - the herdr adapter's start for a new name issues, in this order and each as an argument list never passed through a shell, one pane split with --no-focus, --cwd set to the spec's cwd and one --env KEY=VALUE per env entry including the empty-valued ones, then agent start with the name, --kind claude, --pane set to the pane_id the split returned, and after -- the arguments --model with the spec's model plus --resume with its id only when resume is set, then agent prompt with the name and the spec's prompt and without --wait
  - when agent start reports agent_not_ready and agent get reports blocked, the adapter reads the agent's screen, and only if it contains the text Is this a project you created or one you trust? and the spec's cwd is a linked worktree of the launcher's repository, meaning its .git is a file whose gitdir lies under the git common dir's worktrees directory, sends the keys down then enter exactly once, waits for a settled state, and sends the prompt only if that state is idle or done
  - the trust dialog in a folder that is not such a worktree, any other blocked screen at startup, and a blocked state after the trust answer each get no keys beyond the single trust answer and no prompt, and start raises an error carrying the Handle so the loop can fail the attempt and stop the worker
  - the herdr adapter's session_id returns agent_session.value from the agent list entry whose pane_id is the Handle's when agent_session.kind is id, and None when no entry has that pane_id, when agent_session is null, and when kind is path
  - stop on a Handle whose role is designer issues no herdr command and closes nothing, on FakeLauncher and on the herdr adapter
  - the herdr adapter's stop closes only the Handle's own pane id, never a pane resolved from the agent's name, and never the pane named by HERDR_PANE_ID in the launcher's own environment
  - the herdr adapter's stop records the pane's shell pid, its foreground pids and all of their descendants from a process-table snapshot before it closes the pane, returns only once none of those pids appears in a fresh snapshot, and raises rather than returning normally when any is still present after the stop timeout
  - after stop returns for a Handle whose role is not designer, status for that Handle is gone, on FakeLauncher and on the herdr adapter
  - the default process-table reader, called on Windows, lists the running test process together with its parent pid, and on any other platform raises NotImplementedError when called, and importing it never raises on any platform
  - the herdr adapter's tests drive it only through herdr replies stored as files under tests/test_factory/fixtures/herdr/, the test module records for each file whether it was captured from herdr 0.9.5 or constructed from that version's bundled API schema, and a guard fails any test that reaches the real herdr binary
  - docs/factory/design.md section 8 describes the trust-dialog handling and says pane split takes repeated --env, and section 12 no longer lists the five launcher questions as unverified and lists instead what this ticket could not verify
  - the only files changed are factory/launcher.py, factory/launchers/__init__.py, factory/launchers/herdr.py, factory/launchers/fake.py, new test modules and fixtures under tests/test_factory/, docs/factory/design.md and .factory/220/, so factory/merge.py and its protected set are unchanged
  - pytest from the worktree root reports 0 failed, 0 errors, 0 xfailed, and ruff check, ruff format and pyright at standard are clean on every new file
specified_by: claude
specified_at: 2026-10-22
---

# Spec: the launcher, with herdr behind it

## Source

- Issue #220, its body and the comment carrying #215's results.
- #215's comments: the full live findings of 2026-10-22, in herdr 0.9.5.
- `docs/factory/design.md` §4 rules 1 and 6, §5 (`launcher.py`), §8, §12.
- herdr 0.9.5's own CLI help and bundled API schema (`herdr api schema --json`,
  protocol 22). The help is the authority on syntax.

Where #215 and design §8 disagree, this spec follows #215, as the issue body
says. They disagree in one place: §11/§12's single-variable fallback for
`pane split --env` is unnecessary, because `--env` repeats.

## What #215 settled, and what follows

| Finding | Consequence here |
| --- | --- |
| `pane split --env` repeats, and the env reaches every hook | The adapter passes every variable through the CLI, one `--env` each (criterion 11). The socket API's map is not needed. |
| A fresh folder raises the trust dialog; default "No, exit"; it blocks startup | Recognised by its text and answered, only for linked worktrees of this repository (criteria 12, 13). |
| Any other startup dialog (the MCP approval) also shows as `blocked` | Never answered. Start fails, carrying the Handle (criterion 13). |
| Workers inherit auto mode | Credential stripping is not optional (criteria 3 to 6). |
| `agent_session.value` carries the session id | `session_id` reads it (criterion 14). |
| No `unknown` state was seen | Mapped to working anyway, per the issue and herdr's docs (criterion 9). |

## Facts read off herdr 0.9.5 offline (2026-10-22)

Read-only calls only. No pane was created and no agent started.

- `herdr agent get zz-no-such-agent` exits 1 with
  `{"error":{"code":"agent_not_found",...},"id":"cli:agent:get"}`. That code is
  what `gone` means.
- `agent list` returns `result.agents`, each an `AgentInfo` with `pane_id`,
  `agent_status` and `agent_session` (`{agent, kind, source, value}`, kind `id`
  or `path`, or null). Named agents carry `name`.
- `pane process-info` returns `result.process_info` with `shell_pid` and
  `foreground_processes[].pid`. It does not list background descendants, which
  is why criterion 17 walks a process table.
- `agent start` returns `agent_not_ready` at once when startup is blocked, and
  keeps the name usable for `agent read` and `agent send-keys`.
- CLI server errors are JSON on stderr with exit 1; syntax errors exit 2.

## Decisions I made

- **The credential check lives in `start`, not in `WorkerSpec`.** The issue's
  `WorkerSpec` is a plain record. Every `Launcher.start` refuses a spec without
  the five variables (criterion 6), and `worker_spec` always adds them
  (criterion 5). A spec built by hand therefore cannot reach a worker, and the
  fake's assertion is the same check, so it is testable.
- **`GH_CONFIG_DIR` is `<git-common-dir>/factory/gh-config-empty/`**, beside the
  loop state design §4 rule 5 puts under `<git-common-dir>/factory/`. A
  non-empty directory raises (criterion 4): a worker that ran `gh auth login`
  would otherwise leave a token for every later worker.
- **The trust dialog is answered only in linked worktrees of this repository**,
  identified as #209 does, by `.git` being a file, and by its `gitdir` lying
  under the git common dir. "Worktrees the factory created" has no other
  offline test. The maintainer's own herdr worktrees qualify, which is
  harmless: they are this repository.
- **The answer is `down enter`, once**, from #220's comment. If it is wrong,
  the worker exits or stays blocked, start raises, and the attempt fails. It
  never answers twice and never answers a dialog it does not recognise.
- **A replayed start never re-sends the prompt.** If the loop crashed between
  `agent start` and `agent prompt`, the replay finds the agent and returns it
  idle. The loop then judges an empty turn. A prompt delivered twice is worse.
- **A pane split that crashed before `agent start` is leaked**, not adopted.
  The replay finds no agent by that name and splits a new pane.
- **`stop` waits on a process table, not on herdr.** A pid counts as alive while
  it appears in a fresh snapshot, so a reused pid errs towards waiting, never
  towards declaring the tree gone. The reader is injected. The default uses
  Windows' Toolhelp snapshot through `ctypes`, the standard library, because
  `psutil` is not a declared dependency. On another platform it raises when
  called, so CI on Linux still imports the module.
- **`stop` also refuses the launcher's own pane** (`HERDR_PANE_ID`), the pane
  the loop or the orchestrator is running in. The issue names the designer
  pane; this is the same reason, "you are talking to it".
- **The stop timeout is a parameter with a recorded default**, chosen by the
  plan, not a criterion. It is a herdr timing, not an Expectation about the
  game.
- **`FakeLauncher` lives in `factory/launchers/fake.py`**, not under `tests/`.
  It implements the protocol, it is held to the package's typing gate, and the
  dry run (#223) may need it outside the suite.
- **Roles are strings here.** `roles.py` arrives with #218. The test covers the
  five dispatchable roles named in design §8, and not the orchestrator, which is
  never launched.
- **`CONTEXT.md` gains nothing.** "Worker" and "launcher" are not in the
  glossary. Adding them is outside this ticket's files, and noted in the PR.

## `merge.py`, the protected set, and packaging

`test_every_module_the_console_script_imports_is_protected` walks the static
imports of `factory.__main__` and `factory.cli`. Nothing in that closure will
import `factory.launcher` or `factory.launchers`, so **the test is unaffected
and `merge.py` is not edited** (criterion 22). This was checked by reading the
closure at `9654223`: `cli`, `chain`, `routing`, `hooks`, `models`, `merge`,
`exit_codes`, `__init__` and `__main__`.

Two consequences, stated rather than fixed:

- Until #217 replaces the list with `factory/**`, the launcher's modules are
  not protected. A later `type:chore` PR touching only them could merge itself.
  They feed nothing in the merge verdict, so that is acceptable. This ticket is
  `type:build` and never auto-merges.
- `pyproject.toml` packages `["factory"]` only. The editable install maps the
  package directory, so `factory.launchers` imports. A non-editable build would
  omit the subpackage. `pyproject.toml` is a hard-stop path, so it is not
  changed here. The PR names it for #159, whose loop is the first importer.

## Verification method: suite

Every criterion is settled by a test or by a check on the diff. The adapter
takes an injected command runner and process-table reader, and its tests feed
it recorded replies. Replies from read-only commands can be captured from the
live herdr. Replies from mutating commands (`pane split`, `agent start`,
`agent prompt`, `agent send-keys`, `pane close`) are constructed from the
bundled schema, since creating panes is out of bounds; the test module says
which is which (criterion 20).

## Could not verify (for the PR)

- The adapter against a live herdr. #215 is the live evidence.
- That `--env GH_TOKEN=` with an empty value reaches the worker as empty. #215
  tested only non-empty values. If herdr dropped it, a `GH_TOKEN` in the herdr
  server's environment would leak through.
- The trust dialog's key sequence and option order.
- That closing a herdr pane on Windows ends background descendants. `stop`
  waits for them either way and raises if they outlive the timeout.
- That `credential.helper` reset through `GIT_CONFIG_*` makes a worker's
  `git push` fail on this machine, where Git for Windows' system config sets
  `credential.helper=manager`.

## Not in scope

- The loop (#159), which calls the launcher, persists Handles, and fails
  attempts. Timeouts on a worker's turn are the loop's.
- `roles.py` and the role table (#218).
- `proof.py`'s use of the same environment (design §8), which arrives with it.
- Protecting `factory/**` (#217).
