---
ticket: 220
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "stripped_credentials(common_dir) returns exactly five variables, GH_TOKEN as the empty string, GH_CONFIG_DIR as a directory under the git common dir, GIT_CONFIG_COUNT as 1, GIT_CONFIG_KEY_0 as credential.helper and GIT_CONFIG_VALUE_0 as the empty string, and creates the GH_CONFIG_DIR directory when it is absent"
---

# Spec review: the launcher, with herdr behind it

**Verdict: `changes-requested`.** The spec is careful, and most of it holds
up. It reads #215 correctly, keeps the adapter offline, and is right about the
closure test and the packaging gap.

Two problems block it:

- **The credential set does not do what R11 needs on this machine.** With
  `GH_TOKEN=` and an empty `GH_CONFIG_DIR`, `gh` still finds the maintainer's
  token. Criterion 3 writes that value into the contract. That is why it is the
  criterion quoted above.
- **Failures after the pane split leak the pane.** Criterion 13 covers one
  failure after the trust answer: the worker stays blocked. It misses the
  failure the spec itself predicts for a wrong key: the worker exits.

Three more need a change before the plan: the trust-dialog layout, a race
between the unwaited prompt and `status`, and a `stop` whose wait can pass
vacuously.

Reviewed: `intent.md` and `spec.md` at `4158478`; issue #220 (body and
comment); #215 (all comments); `design.md` §4, §5, §8 and §12; `artifacts.md`;
`.factory/216/spec-review-2.md` (at `ea31605`); `factory/` (`chain.git_dir`,
`cli.ticket_worktrees`, `hooks._common`, `merge.POLICY`);
`test_merge.py`'s closure test; `pyproject.toml`;
`.github/workflows/merge-policy.yml`; `herdr --skill`; and the help for
`agent`, `agent start|get|prompt|read|send-keys|wait|list`, `pane split`,
`pane close`, `pane process-info` and `api`.

## Claims I verified

Every probe ran in my scratchpad, or used read-only herdr calls against an
agent or pane that does not exist. No pane was created and no agent was
started.

- **`agent get` on a closed pane id returns `agent_not_found`.**
  `herdr agent get w99:p999` returns
  `{"error":{"code":"agent_not_found",...}}` and exits 1. So `status` keyed on
  the pane id reads `gone` after `stop`, which criterion 18 needs. Finding 6
  asks for this targeting to be pinned.
- **`pane process-info` on a missing pane returns a different code,
  `pane_not_found`.** That matters for finding 5.
- **herdr's pids are Windows pids, and a ctypes Toolhelp reader sees them.**
  `herdr pane process-info --current` reported `shell_pid` 14456
  (`powershell.exe`) and a foreground `claude.exe` with pid 29840. A
  stdlib-only `CreateToolhelp32Snapshot`/`Process32NextW` prototype found
  both, with 29840's parent as 14456. It walked the tree to eight processes.
  It also reported the test process's own parent pid, equal to `os.getppid()`.
  Criterion 19 is feasible as written.
- **The closure test is unaffected.** `test_every_module_the_console_script_imports_is_protected`
  walks from `factory.__main__` and `factory.cli`, and nothing there will
  import the launcher. `merge.py` need not change.
- **The packaging gap is real.** `pyproject.toml` was copied into the
  scratchpad, beside a stub `factory/launchers/`, and built with
  setuptools 81 (`pip wheel . --no-deps --no-build-isolation`). The wheel held
  only `factory/__init__.py` and `factory/cli.py`. The editable install maps
  `factory` to the directory
  (`__editable___legends_factory_0_1_0_finder.py`, `MAPPING`), so subpackages
  resolve. CI installs with `pip install -e .` (`merge-policy.yml:87`).
- **The `GIT_CONFIG_*` reset defeats Git for Windows' system helper.** This
  answers one of the reviewer brief's questions. The machine runs
  git 2.39.1.windows.1, with `credential.helper manager` in
  `C:/Program Files/Git/etc/gitconfig` (system scope). The test:
  - I set `GIT_CONFIG_SYSTEM` to a file holding a marker helper and a
    URL-scoped `credential.https://example.com.helper`. I set
    `GIT_CONFIG_GLOBAL` to a file holding a third helper.
  - Under `git credential fill`, all three helpers ran.
  - With `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=credential.helper` and
    `GIT_CONFIG_VALUE_0=`, none ran.

  Command-scope config is read after every file, and an empty
  `credential.helper` clears the list collected so far. URL-scoped helpers are
  cleared too. No higher precedence is needed, because none exists.

## Findings

### 1. `GH_TOKEN=` does not stop `gh`, and git has an askpass route around the helper reset (blocking)

**Evidence.** The machine has gh 2.98.0, and `hosts.yml` holds no
`oauth_token`, so the token lives in the Windows keyring. I ran this with the
token redacted from the output:

```
GH_TOKEN= GH_CONFIG_DIR=<empty scratch dir> gh auth token
  -> <TOKEN-REDACTED>, exit 0      (the directory stayed empty)
```

`gh` skips an empty `GH_TOKEN` and falls back to the keyring entry for
`github.com`, and that lookup does not depend on `GH_CONFIG_DIR`. So a worker
built by `worker_spec` can still call GitHub with the maintainer's token. That
is exactly what R11 and the issue ("cannot … call GitHub by mistake") rule
out.

Two more routes, both shown:

- **`GITHUB_TOKEN`.** `GH_TOKEN= GITHUB_TOKEN=from-github-token gh auth token`
  printed `from-github-token`. If the herdr server's environment ever holds
  `GITHUB_TOKEN`, every worker inherits it.
- **An inherited `GIT_ASKPASS`.** This is what VS Code's integrated terminal
  sets. With the five variables set and `GIT_ASKPASS` pointing at a script,
  `git credential fill` returned the script's username and password. The
  helper reset does not touch askpass.

A related consequence belongs under *Could not verify*. Suppose herdr drops an
`--env` with an empty value, which nothing has tested. Then
`GIT_CONFIG_COUNT=1` arrives without `GIT_CONFIG_VALUE_0`, and **every** git
command in the worker fails:

```
error: missing config value GIT_CONFIG_VALUE_0
fatal: unable to parse command-line config
```

That fails closed, but it would stop every Builder.

**Fix.**

- **Criterion 3.** Set `GH_TOKEN` to a non-empty sentinel that GitHub rejects,
  such as `factory-worker-has-no-token`. I checked that `gh auth token` then
  returns the sentinel. A non-empty `GH_TOKEN` also takes precedence over
  `GITHUB_TOKEN`, and makes `gh auth login` refuse. Keep `GH_CONFIG_DIR`.
- **Two more variables, recommended.** Add `GIT_ASKPASS=` and
  `GIT_TERMINAL_PROMPT=0`. With both set, git failed fast ("terminal prompts
  disabled") even with `core.askPass` configured. This also stops a worker's
  `git push` from waiting on the pane's console for a username.
- **Criteria 3, 5 and 6.** Change "exactly five" to the new count.
- **Under *Decisions*.** Record that this departs from the issue's literal
  `GH_TOKEN=`, and why: the literal value does not meet the issue's own goal.
- **Under *Could not verify*.** Replace the `GH_TOKEN` item with the empty
  `GIT_CONFIG_VALUE_0` item above, and its consequence.

### 2. An error after the pane split carries no Handle, so the pane leaks (blocking)

**Evidence.** Criterion 13 makes `start` raise "an error carrying the Handle"
in three cases: a trust dialog outside a worktree, another blocked screen, and
a blocked state after the trust answer.

Criterion 10 sends every other herdr error to "a launcher error", with no
Handle. Some of those errors arrive after `pane split` has already succeeded:

- **The worker exits after the trust answer.** If `down enter` lands on "No,
  exit", Claude exits, and herdr clears the agent's name (`herdr --skill`: a
  name "is cleared when that agent exits"). The settled-state wait then
  returns `agent_not_found`. The spec's own *Decisions* names this as the
  likely failure ("the worker exits or stays blocked"). Criterion 13 covers
  only the second.
- **`agent start` fails in another way.** It can time out (the default is
  30 s) or return any code other than `agent_not_ready`.
- **The state after `agent_not_ready` is not `blocked`.**
- **`agent prompt` fails.**

In each case the loop cannot stop a pane it has no id for. The pane, holding a
shell in a fresh worktree, is left open for good.

Separately, "waits for a settled state" has no bound. `agent wait` without
`--timeout` "waits indefinitely".

**Fix.**

- **Criterion 13.** Every error `start` raises after a successful `pane split`
  carries the Handle. Test the cases above with recorded replies, including
  `agent_not_found` from the wait after the trust answer.
- **Criterion 12.** The wait takes a timeout. The plan picks its value, as it
  does for `stop`.

### 3. The trust answer must check the dialog's layout, its text match must survive wrapping, and the worktree check needs more (changes-requested)

**Is `down enter` safe?** It fails closed in a two-option dialog. Suppose the
default is "No, exit", as #215 recorded:

- if "Yes" sits below "No", `down enter` trusts the folder;
- if "Yes" sits above "No", `down` either wraps around to it or does nothing.
  If it does nothing, `enter` takes "No, exit", and the worker exits.

So it is not dangerous. But it may simply not work. The option order was
never recorded. The layout #215 saw was the one that "lists the folder's
pre-approved permissions", and it appeared because the probe folder had
`.claude/settings.json` hooks. Every Legends worktree has those hooks. Every
snapshot worktree is fresh, so every judge dispatch raises the dialog. If the
order is wrong, every judge dispatch fails.

A dialog with more options, or a different set, would get the same two keys
blind.

**Fix.**

- **Act on one layout only.** Answer only when the screen shows the question
  text, a "No, exit" option, and an option starting "Yes" listed **after** it.
  That is the layout in which `down enter` is right. For any other layout,
  send no keys and raise with the Handle.
- **Read the screen so wrapping cannot hide the text.** Name the read source:
  `agent read --source recent-unwrapped`, or match after collapsing
  whitespace. A narrow split pane can wrap the 46-character question across
  lines, and a plain substring check then fails, silently and closed.
- **Make the worktree check precise.** Resolve a relative `gitdir:` as
  `chain.git_dir` does. Compare resolved paths with `is_relative_to`. Also
  check the back-pointer: `<common>/worktrees/<id>/gitdir` must name
  `<cwd>/.git`. That is git's own pairing, and it rejects a stray `.git` file
  that merely points into `worktrees/`.
- **State the inputs.** Say the adapter is constructed with the git common
  dir. Criterion 6 needs it too, to compare `GH_CONFIG_DIR`.

### 4. An unwaited prompt lets `status` report "finished" before the turn begins (changes-requested)

**Evidence.** Criterion 11 sends `agent prompt` "without `--wait`". herdr's
help says that submission "alone does not prove the agent started a turn".
Criterion 9 maps `idle` to `finished`.

So the loop's first poll after `start` can read `idle` before Claude has picked
up the prompt. The loop would then stop the worker and judge an empty turn. The
issue's "without `--wait`" is about not blocking for the whole turn. It does
not ask for a `status` that can lie.

**Fix.** Pick one:

- **Wait for the turn to start.** `start` sends
  `agent prompt <name> <prompt> --wait --until working --until blocked --timeout <ms>`.
  That returns once activity is seen, not at the end of the turn. A stalled
  prompt (`agent_prompt_stalled`) or a timeout raises with the Handle. Pin the
  argv in criterion 11.
- **Or make `status` refuse `finished` until it has seen `working`.** It must
  not report `finished` until the worker has been seen working since the
  prompt. That is testable with a recorded sequence.

Either way, do not add `--` before the prompt. `herdr agent prompt x -- "-x"`
exits 2 with "unknown option".

### 5. `stop`'s wait can pass vacuously, and it says nothing of a pane already closed (changes-requested)

**Evidence and fix.**

- **A vacuous pass.** Criterion 17 records pids and waits until "none of those
  pids appears in a fresh snapshot". Suppose the reader is broken and returns
  an empty table, or herdr reported pids in another namespace. Then nothing
  ever appears, and `stop` returns at once, reporting the tree gone. **Require
  that `shell_pid` is present in the pre-close snapshot, and raise if not.**
  Add a test with a reader that returns an empty table.
- **Orphans are out of reach.** A parent-pid walk cannot find a process whose
  parent exited before the snapshot. One example is `nohup … &` from a Bash
  call that has already returned. That is close to X3's case. Criterion 17's
  wording ("all of their descendants from a process-table snapshot") is
  testable, but the issue's "returns only once the process tree is gone"
  overclaims. Add this under *Could not verify*, with the closing-a-pane item
  already there.
- **Reused pids.** A reused parent pid can link an unrelated older process
  into the tree. The wait then times out and `stop` raises. That errs the safe
  way, as the spec says. Name it, so a spurious failed attempt is explained.
- **A pane that is already gone.** `pane process-info` on a missing pane
  returns `pane_not_found`. Under criterion 10 that raises, so a `stop`
  replayed after a crash, or a pane the maintainer closed by hand, raises
  forever. Decide what happens, and give it a test. If it stays an error, give
  it its own type, so the loop can tell it apart.

### 6. Pin what `status`, `stop` on a designer and `stop` on the own pane do (minor)

- **`status` targets.** Criterion 9 does not say which target `status` uses.
  Say it is the Handle's pane id, not the name, for the same reason criterion
  16 gives `stop`. The probe above shows that this target yields
  `agent_not_found`, and so `gone`, after a close.
- **`stop` on a designer, or on `HERDR_PANE_ID`.** Criteria 15 and 16 say what
  is not closed, but not what `stop` returns. A silent return breaks the
  protocol's promise that it "returns once the process tree is gone". I
  recommend raising for both. The loop never legitimately asks for either.
  Whatever is chosen, the tests should assert it.

### 7. The packaging gap goes to the maintainer, not to #159 (minor)

The spec's analysis is right (see *Claims I verified*). But handing the gap to
#159 hands it to another agent, and `pyproject.toml` is a hard-stop path
(`merge.POLICY.hard_stop_paths`) for that agent too.

Put it in the PR's "what a human still has to do", with the exact edit:
`packages = ["factory", "factory.launchers"]`, or `packages.find` with
`include = ["factory*"]`.

## On width: 23 criteria is acceptable, and no split is needed

The criteria are fine-grained, not broad. Criteria 21 to 23 are boilerplate,
and 1 to 8 are small record and fake checks. The risk is concentrated in 12,
13 and 17, and splitting the ticket would not reduce it.

If the plan's radius grows, the natural cut is:

- A: `launcher.py` with the credentials, `worker_spec` and the fake, which is
  all #222 needs;
- B: the herdr adapter.

Do not cut it pre-emptively.

## Notes, not findings

- **Scrub captured fixtures.** A live `agent list` or `pane process-info`
  includes session ids, the maintainer's paths and full command lines. Trim
  captures to the fields the adapter reads.
- **Prompt length.** The prompt travels as one argv element. A Windows command
  line is capped at 32,767 characters, so keep role prompts short, pointing at
  files.
- **An optional idempotency guard.** On an idempotent hit, `agent get` returns
  the agent's `cwd`. Comparing it with `spec.cwd` would cheaply catch a name
  collision.

## What this review could not verify

- **The trust dialog's option order, and whether `down` wraps around.**
  Recording them needs a live blocked agent.
- **Whether herdr's `pane split --env KEY=` with an empty value parses and
  reaches the process.** I could not probe it without risking a pane.
- **Whether `GCM` or other helpers are reached by a route other than
  `credential.helper` and askpass.** I tested the system-scope reset with
  `GIT_CONFIG_SYSTEM` and marker helpers, not with the real `manager`
  against github.com, which might have shown a prompt or used a stored
  credential.
- **The suite.** I did not run pytest, because no source changed.
