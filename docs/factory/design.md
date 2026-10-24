# The factory: design

**Status: agreed 2026-10-22, read against `4296edc`. Nothing in it is built except what §3 says holds today. Each part becomes true when its §10 ticket merges.**

This is the factory's design: what it is, how it is built, and in what order. It merges four documents reviewed in the maintainer's checkout under `.lavish/` (gitignored):

- the agreed lifecycle;
- the architecture;
- an independent review (findings B1–B3, M1–M9, m1–m8);
- an independent re-check of the merged result (X1–X8, a–i).

Every amendment is folded into the sentence it corrects. §13 says where each finding went.

Claims about current code were read at `4296edc` (`movements-improvements`, after #213).

**The documents this supersedes.** [stages.md](stages.md), [roles.md](roles.md), [artifacts.md](artifacts.md) and [bootstrap.md](bootstrap.md) describe the factory **as it runs today**. They stay true of today until the roadmap ticket owning each part lands and updates them. Where they and this document disagree about the *target*, this document wins. Where they describe *today*, they win.

**Definition of done.** A real bot ticket goes from the maintainer's request to an open PR, with the maintainer doing nothing but agreeing the spec. That is #224.

---

## 0 · Rulings

All eleven were accepted at these defaults on 2026-10-22.

| # | Question | Decided |
| --- | --- | --- |
| R1 | Order of the intake | Spec review, then plan, then **accept**. **The maintainer reads the spec, never the plan.** Accept records the plan's radius on its own and shows one line: "hard-stop paths: none", or the paths themselves when the radius touches the input path, an ADR area or map JSON. *(Amended the same day: the maintainer approves what, not how.)* |
| R2 | What drives the machine | `factory run`: a long-lived loop in its own pane. You start it once. It never exits on its own. |
| R3 | When a spec is finished | When the maintainer says so, the Designer runs `factory spec submit`. Only submitted specs are reviewed. |
| R4 | Caps | 2 attempts per stage. 2 cycles per judged stage: spec review, code review, QA. Then the ticket parks. |
| R5 | Spec gaps | The Designer answers in `answers.md`. `spec.md` is frozen after acceptance. An answer that would change a criterion parks the ticket for the maintainer. |
| R6 | Splitting a feature | One feature, one ticket, until done. Children and epics come after. |
| R7 | Tickets that need the game | A `method: live` or `both` ticket stops at QA and parks until the QA phase gives agents a running client. The done ticket is `method: suite`. |
| R8 | Keeping acceptance the maintainer's | `factory accept` asks for the ticket number to be typed on a real terminal, and refuses when stdin is not a terminal. |
| R9 | Documentation | **Reversed 2026-10-22 (#218).** The Document stage stays, between the proof and review. A Documenter fills `docs_cleared`, writing only documentation outside every hard-stop and protected path, and the Reviewer judges it. |
| R10 | First unattended run | A factory ticket as a dry run (#223), then the bot ticket (#224). |
| R11 | Credentials | Workers hold no GitHub token and no git credential helper. Only the factory loop pushes and opens PRs. The maintainer adds a ruleset requiring PRs on `dev`. |

## 1 · The shape, in four sentences

1. **The factory loop is the gate; the hooks are early warning.** After every dispatched turn, the loop judges the changes from its own process, with the merged code, before it commits or advances anything. A worker can switch its hooks off. It cannot switch off the process that judges its turn.
2. **Judges work on a snapshot.** The Spec Reviewer, Planner and Reviewer each run in a throwaway worktree at the exact commit they judge. The loop copies back their one artifact and stamps which commit it was.
3. **The loop writes every binding fact.** It records the submitted commit, the proven commit, the suite and red-test outcomes (`proof.md`), and the accepted blob. Its counters live outside every worktree.
4. **Smaller than it was.** There are no children, no epic, no `split.toml`, no command registry and no `gates/` package. The stages are close to today's stages.

## 2 · The lifecycle

```
you: "I want X"
  -> factory feature new <title> | --issue <n>
     issue, ticket branch + worktree, Designer in its own worktree, in your pane
you iterate with the Designer, then say "submit"
  -> Designer runs factory spec submit; the loop copies intent/spec into the ticket branch
  -> Spec Reviewer (snapshot at the submitted commit)   changes-requested -> Designer (<= 2 cycles)
  -> Planner (same snapshot) writes plan.md: radius + approach
you: factory accept <n>  -- reads the spec and the hard-stop line, types the number
=========================== you are out from here ===========================
  -> Builder turn (ticket worktree) -> the loop stops it, judges, commits, proves -> proof.md
  -> Documenter (ticket worktree) updates the coupled docs and fills docs_cleared
  -> Reviewer (snapshot at proof.md's commit)   changes-requested -> Builder (<= 2 cycles)
  -> QA: method suite -> skipped; live/both -> parks until the QA phase (R7)
  -> the loop pushes and opens the PR   <- DONE
you merge (after done: by rule)
anywhere: 2 attempts, 2 cycles, or factory park -> parked, ready-for-human; the Orchestrator tells you
```

| Stage | Who acts, and where | What the loop settles | Leaves when |
| --- | --- | --- | --- |
| `design` | The Designer, in its own worktree, in a pane you talk to | Nothing. Never dispatched. | `spec submit` recorded a commit |
| `spec-review` | The Spec Reviewer, on a snapshot at the submitted commit | Copies `spec-review.md` back and stamps `commit` | `pass` for the current submission. `changes-requested` returns to design as a cycle. |
| `build-planning` | The Planner, on the same snapshot | Copies `plan.md` back, stamps `plan.commit`, and runs `plan check` | A valid radius planned against the current submission |
| `accept` | **You**, with `factory accept <n>` | Writes `acceptance.md`, and records the accepted blob in its own state | The acceptance matches the loop's record and the spec blob at HEAD |
| `build-implementing` | The Builder, in the ticket worktree | Stops, judges, commits and proves each turn | `proof.md` is current for the source at HEAD |
| `document` | The Documenter, in the ticket worktree | Judges the turn like the Builder's, against the Documenter's write scope | `docs_cleared` is filled (the list may be empty) |
| `review` | The Reviewer, on a snapshot at `proof.md`'s commit | Copies `review.md` back and stamps `commit` | `pass`, and current when its loop-stamped `commit` is the commit that wrote the current `proof.md`. `changes-requested` returns to the Builder as a cycle. `fail` parks. |
| `qa` | Nobody, until the QA phase | A live ticket parks here | — |
| `integrate` | The loop | Checks the base diff, pushes, opens the PR | A PR is open. Done. |

**Gone from today's stages:** `plan` and the Clerk (the Designer writes the intent), and `test` (the loop proves). **Kept, and moved:** `document` now sits between the proof and review (R9 reversed). **Moved:** acceptance, from the intent before design, to the spec before build.

## 3 · What holds today, at 4296edc

| Rule | Today | Why |
| --- | --- | --- |
| Artifacts exist before code | partly | Edit tools only. `.claude/settings.json` matches `Write\|Edit\|MultiEdit\|NotebookEdit`, so shell writes bypass it (#207). |
| The spec was reviewed by someone else | existence only | `decide_write` checks that `spec-review.md` exists. Routing never reads the verdict. Eight of nine committed `spec-review.md` files say `changes-requested`. #202's says `pass-with-notes`, which is outside `VERDICTS`. |
| A proof was recorded before finishing | bypassable | `_source_changed` reads `git status --porcelain` (cli.py:277), so committing first skips `decide_stop` (hooks.py:196). Any earlier `proof.suite` also satisfies it (chain.py:199). |
| No source in the primary checkout | enforced at the tool | #213, row 1 of `decide_write` (hooks.py:140), before any branch is consulted. Shell writes are not covered. |
| Merge conditions | not live | The workflow is not on `dev`, the default branch (at `4296edc`). On 2026-10-22: no branch protection, no rulesets, and no `permissions` block in `.claude/settings.json`. |
| Honest review, inside the radius, no shared paths, never picks its stage, capped, nothing merges without QA | no | None exists in code. |

**Defects, all reproduced by the reviews:**

- **d1. A rejected review can never be left.** Routing matches the verdict alone (routing.py:209–216). `test_a_rejected_review_goes_back_to_the_builder` pins one hop.
- **d2. `factory next <n>` and `factory model <n>` read the cwd's chain** (cli.py:98, 138).
- **d3. Stop is refused because of another ticket.** `_stop_everywhere` (`factory/cli.py`) judged every ticket worktree. Fixed by #207: it judges the session's own worktree plus the worktrees in its write log.
- **d4. The hook runs the worktree's own gate code.** `factory-hook.sh` execs `python -m factory`, and `-m` puts the cwd first on the import path. The hook script and `settings.json` are themselves read from the worktree via `CLAUDE_PROJECT_DIR`.
- **d5. `merge-policy.md` is wrong in both directions, and its test passes.** It denies that `.factory/**` is allowlisted (it is, merge.py:72). It lists `.claude/**` as allowlisted (line 40; it is not). The test checks only that each value appears.
- **d6. Merged tickets do not close themselves.** PRs target `movements-improvements`, not the default branch, so "Closes #n" never fires. The cause was fixed on 2026-10-22: `dev` is now the default branch and the one PRs target. #140, #162, #206 and #209 stayed open after merging, until they were closed by hand in the 2026-10-22 cleanup.

## 4 · Rules the architecture follows

1. **Decisions are pure functions of a snapshot.** `loop.plan(snapshot) -> actions`, as `routing`, `models` and `merge.evaluate` are today. Git, GitHub and herdr sit behind adapters that tests fake.
2. **The loop judges every dispatched turn, from its own process.** The order is fixed:
   - **Stop the worker first.** "Idle" is not "stopped": a background task can wake it.
   - Take the turn's diff: `turn_base..HEAD`, plus uncommitted and untracked changes, plus ignored files under `.claude/`.
   - Run the same per-path rules the hooks run over every path in the diff, **except `.claude/` files**. Claude Code writes `settings.local.json` itself, so those are judged by `hooks_disabled` instead, which parses them (§7, last row). Then run the repo's pre-commit.
   - Compare a **fingerprint** of what lives outside the worktree and could change the judge. A change parks the ticket. The fingerprint covers:
     - the primary checkout's `factory/` and `.claude/`;
     - `~/.claude/settings*.json`;
     - `<git-common-dir>/config` and `hooks/`;
     - the base.
   - **Pass**: commit with git hooks off. **Fail**: a failed attempt. The turn is saved to `refs/factory/<n>/rejected/<attempt>`, and the worktree is reset to `turn_base`.

   `turn_base` is held in memory for the turn, and must be an ancestor of HEAD.
3. **A judge never shares a worktree with the work it judges.** It runs on a detached snapshot, and the loop copies back exactly one file. That copy-back *is* the judge's write scope. Afterwards the loop asserts that the ticket worktree's HEAD and `status --ignored` are unchanged, since a judge could write there by absolute path. **The same assertion follows every proof run**, which executes Builder-written code (§6).
4. **One writer per worktree, by construction.** The Designer has **its own worktree** and is never dispatched. The loop copies `intent.md`, `spec.md` and `answers.md` into the ticket branch by pathspec. The Builder alone writes the ticket worktree, and only after acceptance. The loop refuses to dispatch into a dirty worktree.
5. **Loop state lives outside the worktrees**, in `<git-common-dir>/factory/<n>/state.json`. It is rendered into the chain as `run.md` once, just before the PR. The accepted spec blob and the base SHA are recorded there at acceptance, so a hand-written `acceptance.md` accepts nothing.
6. **Every gate guards against error, not intent.** A worker can unset its env through the shell. What this design guarantees is that such a turn fails judgement and is recorded. It cannot slip through quietly.
7. **The loop's git never runs code a worker could have written.** Every loop git call runs with `-c core.hooksPath=<empty> -c core.fsmonitor=false`. Pre-commit runs as part of judgement instead.

## 5 · Modules

| Module | Status | Responsibility |
| --- | --- | --- |
| `cli.py` | kept | Dispatcher, `_emit`, the exit-code contract. `COMMANDS` stays a plain dict. A registry was considered and dropped: protecting `factory/**` removes the `merge.py` collision, and a `COMMANDS` entry is a one-line conflict. |
| `chain.py` | extends | Block lists (`criteria`, `radius`; skipped today at chain.py:122). New artifacts: `spec_review`, `acceptance`, `proof`, `answers`, `park`. `blob(repo, commit, path)` returns git's blob id, independent of line endings. Radius syntax is files and `dir/**` only. `intent.md: chain: 2` marks a v2 chain; absence means v1. |
| `routing.py` | rows change | **Two tables.** v1 chains keep today's rows, unchanged, because every roadmap ticket is worked by hand under v1 until #223. v2 chains get the §2 stages: the verdict for the current submission, `plan.commit` bound to it, acceptance matching the loop's record, `proof.md` currency, review staleness, caps, and `park.md`. |
| `roles.py` | new | Role → stage (the Documenter owns `document`), runs-in (`worktree\|snapshot\|own-worktree`; the designer is the only `own-worktree` role), write scope, allowed commands, model key. [roles.md](roles.md) states it, and a test keeps the two equal. |
| `hooks.py` | extends | Role-scope and radius rows in `decide_write`, keyed on `FACTORY_ROLE`. Plus `judge_paths(root, paths, role)`, which the loop calls with a turn's diff. `decide_stop` judges the session's own worktree, plus the worktrees an off-ticket session wrote into. |
| `worktrees.py` | moved | `ticket_worktrees` from cli.py, plus `worktree_for(n)` (d2). |
| `state.py` | new | `state.json`, written atomically, and `render_run_md`. `turn_base` is stored for the record, but the loop never trusts it back from disk during a turn (§4.2). |
| `proof.py` | new | Runs in throwaway worktrees, with stripped credentials. It checks the suite shape at HEAD, and then `red_test` against base (§6). |
| `loop.py` | new | `factory/loop.py`. `snapshot()`; `plan(snapshot)`, which is pure; `apply()`. The actions are `Dispatch`, `JudgeTurn`, `CopyBack`, `Prove`, `Park`, `OpenPR` and `Reap`. `Reap` never closes a designer pane. |
| `gitops.py`, `github.py` | new | Snapshots, copy-back, pathspec commits with an `index.lock` retry, turn diff, rejected refs, `hooks_disabled`, fingerprint, `assert_untouched`. `run_gh` moves out of merge.py. **Only these modules hold credentials.** |
| `launcher.py`, `launchers/herdr.py` | new | §8 |
| `merge.py` | small | `protected_paths` becomes `factory/**`. The hard-stop globs stay here. |
| `models.py` | kept | The table gains `spec-review`, loses `plan` and `test`, moves `qa` to `complex`, and gains a `[roles]` block and the `attempt_at_least` retry escalation (#218), in the same PR as the `Stage` enum (models.py:162–170 rejects unknown keys). |

## 6 · Artifacts and who writes them

| File | Writer | Fields |
| --- | --- | --- |
| `intent.md`, `spec.md` | Designer, copied in by the loop | As today, plus `chain: 2`. `criteria` and `method` are now read. `accepted_by` is retired for v2. |
| `spec-review.md` | Spec Reviewer, stamped by the loop | `verdict`, `reviewed_by`; `commit` (written by the loop) |
| `plan.md` | Planner, then Builder, then Documenter (`docs_cleared` only) | `radius` (files, `dir/**`), `red_test` (or `none` with `kind: refactor\|test-only`), `docs_cleared`, a required **`## Could not verify`** section, and `plan.commit` (written by the loop). The Builder may narrow the radius, never widen it. |
| `acceptance.md` | `factory accept` | `accepted_by`, `accepted_at`, `commit`, `spec_blob`, `radius` (copied verbatim), `hard_stop_approved`, `base_sha`. Valid only when it matches the loop's record. |
| `proof.md` | the loop only | `commit`, `suite: pass\|fail`, `red: red\|green\|error\|none`, `red_test`, output digests, `base_sha`. Current when no source differs between `commit` and HEAD, ignoring `.factory/`. |
| `review.md` | Reviewer, stamped by the loop | `verdict`; `commit` (written by the loop). The Reviewer judged a snapshot at `proof.md`'s own commit, so `commit` never equals `proof.commit`. The review is **current when its loop-stamped `commit` is the commit that wrote the current `proof.md`**. The loop proves after every Builder turn that passes judgement, so any proven Builder turn, even one touching only `plan.md`, makes the review stale. A turn that fails judgement writes no new `proof.md`, so the review stands and the attempt cap applies. That is what ends the loop in d1. *The staleness rule, with the Documenter's turn between the proof and the review, is settled by #237.* |
| `answers.md` | Designer, copied in by the loop | Appended answers to spec gaps |
| `park.md` | any worker, via `factory park` | `ticket`, `kind: needs-human\|spec-gap`, `stage`, `parked_at`, with the reason in the body |
| `run.md` | the loop, once | `state.json` rendered, committed just before the PR |

**The red test, precisely.** In a throwaway worktree at HEAD:

- **The test side** (`tests/**`, `conftest.py`, `pytest.ini`) stays at HEAD.
- **Everything else** is restored to `base_sha`. Files the change added are deleted, and files it deleted are restored.
- Run `red_test`, then classify:
  - **`red`**: pytest exits 1, and the nodeid is among the junitxml failures.
  - **`error`**: collection fails, the nodeid is not collected, or a marker deselects it. This counts as no proof.
  - **`green`**: the test passed without the change, so it does not test it.
  - **`none`**: declared by the plan, and judged by the Reviewer.

**The suite.** Checked by shape from junitxml, not by exit code: 0 failed, 0 errors, 0 xfailed, and every deselected test belonging to an opt-in marker. It takes about 60 s at `4296edc`.

**Line endings.** #217 adds a `.gitattributes` with `.factory/** text eol=lf`. None exists at `4296edc`. Either way, hashes are always git blob ids, never byte hashes.

**`configs/factory.toml`**, created by #218 and owned by the maintainer: `attempts = 2`, `cycles = 2`, `wip = 1`, `launcher = "herdr"`, `worker_timeout_min`, `poll_s`. It is outside the merge allowlist, so it never auto-merges.

## 7 · The eleven rules, and where each is enforced

There are three layers. The **hook** reports early, at the tool call. The **loop** is binding, judging each dispatched turn. **GitHub** guards what reaches the remote.

| Rule | Hook (early) | Loop (binding) | Residual |
| --- | --- | --- | --- |
| Artifacts before code | PreToolUse, as today | A source change before acceptance is a failed turn | — |
| Spec reviewed by someone else | — | A separate session on a snapshot. The verdict is read for the current submission. | That the judge was honest |
| Proof before finishing | Stop: a Builder needs `plan.md` and a filled *Could not verify* | The loop proves. No worker writes the proof. | A weak `red_test`, which the Reviewer judges |
| No source in the primary checkout | PreToolUse (#213) | Never dispatched there | Shell writes in a session the maintainer opens |
| Merge conditions | `permissions.deny` on `gh pr merge` | Workers hold no credentials. The loop never merges. | After done: the workflow and `qa-passed` |
| Honest review | PreToolUse role scope | Copy-back for judges. A Builder turn touching another role's file fails. | — |
| Inside the radius | PreToolUse, against `plan.md` and `acceptance.radius` | Every path in the turn diff. Plus hard-stop paths not in `hard_stop_approved`. Plus `base_sha...HEAD` against the radius **and the hard-stop list** at accept and at OpenPR, failing closed, which catches commits made outside a judged turn. | — |
| No two tickets on one path | — | Not needed at `wip = 1`. After done: the radius lock. | Deferred |
| Never picks its own stage | SessionStart states `FACTORY_STAGE` | The loop chooses the stage. Writing another stage's artifact fails the turn. | — |
| 2 attempts, 2 cycles | — | `state.json` counters, then park and label `ready-for-human` | A rate-limited worker costs an attempt |
| Nothing merges without QA | — | A live ticket parks at QA (R7) | After done |
| *Gates disabled from inside* | The hook runs the primary's code (`python -I`). The heartbeat prints the primary's HEAD and whether it is dirty. | `hooks_disabled` parses `.claude/settings*.json` and refuses only `env.FACTORY_HOOKS`, `disableAllHooks`, `hooks`, and changes to tracked `.claude/` files. Claude Code writes `settings.local.json` itself, so a byte comparison would park everything. Plus the fingerprint. | A ticket whose radius includes `.claude/**` is never dispatched. It parks for a person. |

## 8 · Workers and the launcher

| Role | Runs in | Writes | May run |
| --- | --- | --- | --- |
| designer | its own worktree, in your pane, resumable | `intent.md`, `spec.md` (until submit), `answers.md` | `spec submit`, `park`, `next` |
| spec-reviewer | snapshot | `spec-review.md` (copied back) | `park` |
| planner | snapshot | `plan.md` (copied back) | `park`, `plan check` |
| builder | ticket worktree | source in the radius, tests, `plan.md` | `park`, `next`, `plan check` |
| documenter | ticket worktree | docs, `AGENTS.md` files and `CONTEXT.md` outside every hard-stop and protected path, `plan.md`, `park.md` | `doc check`, `park`, `next` |
| reviewer | snapshot at `proof.md`'s commit | `review.md` (copied back) | `park` |
| orchestrator | primary checkout, your pane | nothing | `status`, `run`, `feature new`, `next` |

Every command checks the caller's role against this table. No role means a session the maintainer opened, which may run anything, except that `accept` still needs a terminal.

```python
class WorkerSpec:            # frozen
    name: str                # t233-builder-1
    cwd: Path
    env: Mapping[str, str]   # FACTORY_ROLE, FACTORY_STAGE, FACTORY_TICKET + stripped credentials
    model: str
    prompt: str
    resume: str | None       # designer only

class Launcher(Protocol):
    def start(self, s: WorkerSpec) -> Handle: ...     # idempotent by name
    def status(self, h: Handle) -> WorkerState: ...   # working | finished | blocked | gone
    def session_id(self, h: Handle) -> str | None: ...
    def stop(self, h: Handle) -> None: ...            # returns once the process tree is gone
```

**herdr.** Syntax is herdr 0.9.5's own `--help`. Every command is an argument list, never a shell string, and every command after `agent start` targets the pane id, not the name.

- **`start`** checks its per-process record of the Handles it started, then `agent get <name>`, so replaying after a crash never starts a second worker. A replay that finds the agent returns a Handle marked "prompt not seen to start", so its idle reads as `blocked`, never finished, and the prompt is never sent twice. A new name takes `pane split --pane $HERDR_PANE_ID --no-focus --cwd <cwd>` (it raises before splitting when `HERDR_PANE_ID` is unset, because herdr would otherwise split whichever pane is focused) with one repeated `--env KEY=VALUE` per variable, empty-valued ones included; then `agent start <name> --kind claude --pane <id> --timeout -- --model <m> [--resume <id>]`; then `agent prompt <id> <text> --wait --until working --until blocked --timeout`, which returns at the first activity rather than at the end of the turn. Any failure after the split carries the Handle, so the loop can stop the pane.
- **`status`** calls `agent get` with the pane id. `working` and `unknown` are working, `idle` and `done` are finished (blocked, for a Handle whose prompt was not seen to start), `blocked` is blocked, `agent_not_found` is gone. Any other code, a reply that is not JSON, and a status outside herdr's five raise; none is mapped.
- **`session_id`** reads `agent_session.value` from the `agent list` entry for the pane when its kind is `id`, and is `None` otherwise.
- **`stop`** raises for a designer and for the launcher's own pane (`HERDR_PANE_ID`). It requires herdr's `shell_pid` in a process-table snapshot, records that pid, the foreground pids and all their descendants, closes the pane, and returns only once none is in a fresh snapshot, or raises after a timeout. `pane_not_found` means already stopped. The snapshot is Windows Toolhelp through `ctypes`; elsewhere it raises when called.

**What #215 answered besides the launcher.** Workers inherit the maintainer's auto permission mode, which is why credential stripping is not optional. Hooks fire in that mode. A worker's Bash terminal is unreliable (`GetConsoleMode` fails), so nothing a worker runs may depend on one (see #222).

**The trust dialog.** A fresh folder raises Claude Code's folder-trust dialog; its default is "No, exit", and it blocks startup (`agent_not_ready`, then `blocked`). The adapter reads the screen with `agent read --source recent-unwrapped`, collapses whitespace, and sends `down` then `enter` once only when the text is the question followed by "No, exit" and then, with only whitespace between, "Yes", and the cwd is a linked worktree of this repository (git's `gitdir` pairing, compared as resolved paths). Any other layout, and any other blocked screen such as the MCP approval, is never answered: start raises with the Handle. The live screen, captured in herdr 0.9.5, does not number its options.

**Credentials (R11).** Each worker gets eight variables, from `stripped_credentials`: `GH_TOKEN=factory-worker-has-no-credentials` (non-empty, because an empty one lets gh read the keyring), `GH_CONFIG_DIR=<git-common-dir>/factory/gh-config-empty` (an empty directory; a non-empty one raises), `GITHUB_TOKEN=`, `GIT_ASKPASS=`, `GIT_TERMINAL_PROMPT=0`, and `credential.helper` reset through `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0`, `GIT_CONFIG_VALUE_0=`. `worker_spec` always adds them; every launcher's `start` refuses a spec that lacks one or differs. `proof.py` uses the same environment.

**One `factory run` at a time**, through an OS lock that dies with the process. The dispatch record is written before the worker starts. `run` re-execs itself when the primary checkout's HEAD changes (§9).

## 9 · Commands

Exit codes: 0 pass · 1 gate failed · 2 misuse · 3 needs a human. Every command supports `--json`.

| Command | Who | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| `feature new <title> \| --issue <n>` | you, Orchestrator | issue (or the existing one), branch, worktrees, Designer started | — | bad args; a role not allowed | gh, git or herdr failed |
| `spec submit` | Designer | copied in and committed; submission recorded | no `criteria` or `method` | not a ticket; after acceptance | — |
| `accept <n>` | you | `acceptance.md` committed, and the loop's record written | review not `pass` for this submission; no valid plan; the base diff is outside the radius or touches an unapproved hard-stop path | not a terminal; wrong number typed | — |
| `run` | you, once; re-execs itself when the primary checkout's HEAD changes | stopped by you | — | another `run` holds the lock | — |
| `run --once` | tests | acted, nothing needs you | an attempt failed | misuse | something parked |
| `status` | anyone | nothing parked | — | — | parked items, each with its reason |
| `park [<n>] --reason \| --question` | a worker | `park.md` written, in the ticket's own worktree | — | flag misuse, an empty text, no ticket, or the ticket lookup's 2 (no worktree on `issue/<n>-*`) | the ticket lookup's 3 (several worktrees), or `park.md` already exists (the kind recorded is named; nothing is written) |
| `next [<n>]` | anyone | stage, read from the ticket's own worktree | — | not a ticket; `FACTORY_STAGE` disagrees | blocked, parked, or awaiting you |
| `plan check [<n>]` | Planner, Builder | radius valid, inside acceptance | empty, malformed, or widened | misuse | an unapproved hard-stop path |

`version`, `model`, `merge check` and `hook` are unchanged, except that `model <n>` reads the ticket's own worktree.

The PR is opened by the loop's `OpenPR` action. That action:

- first checks every non-`.factory` path in `base_sha...HEAD` against `acceptance.radius` and `hard_stop_approved`, failing closed (X5);
- then commits `run.md`, pushes, and opens the PR;
- exits 1 when *Could not verify* is empty.

**The Orchestrator** is the agent you talk to about everything in flight. It answers from `factory status --json`, never from memory. It may start `run` and `feature new`. It chooses no stage, role, model or retry, it cannot accept, and it writes nothing. It needs a `roles.py` row, a prompt, and a `status --json` detailed enough to answer from.

## 10 · Build order

Order is held by GitHub's *blocked by* links. The epic is #171. The blockers below are as GitHub held them on 2026-10-22. The ids are names, not milestones: P1 (#219) sits in milestone *Factory P0*. **Every ticket below is worked by hand under v1 routing until #159 exists.**

| Milestone | Ticket | What | Blocked by |
| --- | --- | --- | --- |
| P0 | #214 D1 | This document | — |
| P0 | #215 L0 | The five launcher questions, in real herdr | #214 |
| P0 | #216 S1 | The hook runs the main checkout's gate code | #214 |
| P0 | #217 S2 | `factory/**` protected; `worktree_for`; `merge-policy.md` true; `.gitattributes` | #216 |
| P0 | #207 S3 | Stop judges the session's own worktree, plus off-ticket targets | #217 |
| P0 | #139 S4 | Chain v2 | #214 |
| P0 | #219 P1 | Loop state, `factory park` | #207 |
| P0 | #218 S5 | `roles.py`, the models table with retry escalation, `configs/factory.toml`; the `Stage` enum | #139, #219 |
| P0 | #237 S5b | Routing v2 rows (v1 kept) | #218 |
| P1 | #220 P2 | Launcher, credential stripping | #215, #207 |
| P1 | #221 P3 | Git and GitHub adapters | #207 |
| P1 | #222 P4 | `feature new`, `spec submit`, `accept` | #219, #220, #221, #218 |
| P1 | #163 P5 | Role scopes and radius; `judge_paths` | #139, #218, #207 |
| P1 | #145 P6 | The loop proves; `proof.md` | #221, #139 |
| P1 | #143 P7 | `plan check` | #139, #218 |
| P1 | #152 P8 | Role prompts and the review policy | #218 |
| P2 | #159 E1 | The factory loop: `run`, `status`, `OpenPR` | #218, #237, #219–#222, #163, #145, #143, #152 |
| P2 | #223 E2 | Dry run on a factory ticket | #159 |
| P2 | #224 DONE | A bot ticket, request to open PR | #223 |

**Only the maintainer can do these two:**

- the `gh pr merge` deny in `.claude/settings.json`;
- the ruleset on `dev`.

## 11 · Not built before done

| Item | Why | Tickets |
| --- | --- | --- |
| Children, epics, `split.toml` | R6. When they return, the split carries a spec blob, allows interface criteria, cuts children after their predecessors merge, and makes answers visible to children. | — |
| QA, and agents with a running client | R7 | #154–#158, #167–#169 |
| Merging by rule, CI on the right branch, closing issues on merge | Done ends at an open PR | #151, #160 |
| The radius lock | `wip = 1` | — |
| Command registry, `gates/` package | Only if conflicts hurt | — |
| Doc lints and the scheduled audit | Per-change docs ride the Document stage (#186). Keeping docs current *between* changes is upkeep, not one ticket reaching a PR | #228, #181–#184, #187, #188 |
| Poller, metrics, bands, in-ticket parallelism | Volume, not one ticket, and R6 | #164–#166, #170 |
| Housekeeping | Not on the critical path; any session may pick these up | #136, #210 |
| Harnesses other than Claude Code | `FACTORY_ROLE` keeps the gates portable | — |

## 12 · Not verified

- Whether herdr passes an empty `--env` value through. If it drops `GIT_CONFIG_VALUE_0=`, every git command in a worker fails; if it drops `GITHUB_TOKEN=` or `GIT_ASKPASS=`, an inherited value gets through.
- Whether herdr resolves a pane id (not only a name) for `agent read` and `agent send-keys` while startup is blocked. If it does not, the read returns `agent_not_found` and every dispatch into a fresh worktree fails, closed. Also unverified live: how repeated splits of the loop's own pane behave.
- Whether `down` then `enter` trusts the folder in every case: it did in one live run, in herdr 0.9.5.
- That closing a herdr pane on Windows ends background descendants. A parent-pid walk cannot see an orphan whose parent already exited, so "the process tree is gone" holds only for the tree the snapshot shows.
- Whether Git Credential Manager is reachable by a route other than `credential.helper` and askpass.
- Whether a background Bash task re-invokes an idle Claude session, and how herdr reports it. The loop stops workers before judging either way.
- Whether Claude Code writes `settings.local.json` inside a worktree when something is approved there. This is inferred from the primary checkout's file.
- Whether the suite writes untracked, non-ignored files.
- Whether `claude --resume` is safe while the original Designer session is open.
- Whether `python -I -m factory`, run from a worktree, loads the primary checkout's code in the hook's real environment. The re-check's spot check reported that it does from a plain directory holding a fake `factory/`. That was relayed in-session on 2026-10-22 and is recorded in no file. #216's tests prove it.
- Whether a ruleset with no bypass actors binds the maintainer's admin token.

## 13 · Finding ledger

**How:**

- *taken* means the reviewer's fix, as given.
- *changed* means the problem is solved another way, and the row says how.
- *deferred* means it is settled by a later ticket.
- *fixed* means a stale fact was corrected.

The first review:

| Id | Finding | How | Where it is settled |
| --- | --- | --- | --- |
| B1 | Stop over `base...HEAD` refuses later workers | taken | §4.2: the loop judges turns. §7: base-diff radius checks at accept and OpenPR (X5). |
| B2 | `proof.commit = HEAD` cannot be satisfied | taken | §6 `proof.md`: compare source, not commits |
| B3 | Stop refused for another ticket | taken | #207 judges the session's own worktree, plus a per-session target log for off-ticket sessions (X7) |
| M1 | A draft and a finished spec are one state | taken | R3, `spec submit` |
| M2 | Concurrent writers; Reap closes the Designer | taken | §4.3–4.5; the Designer in its own worktree (X2) |
| M3 | Gates switched off from inside a worktree | taken | `python -I` (#216); §7's last row; the fingerprint |
| M4 | Acceptance rests on an env var | taken | R8; §8's command table; the loop's acceptance record |
| M5 | Workers hold credentials | taken | R11; §8 |
| M6 | Bindings written by those they judge | taken | §1.3; stamped `commit` fields; `proof.md` |
| M7 | Byte hashes vs `autocrlf` | taken | blob ids; `.gitattributes` |
| M8 | N > 1 does not work | changed | the accepted radius comes from `plan.md`, so `split.toml` is not needed; R6; §11 |
| M9 | No artifact holds *Could not verify* | taken | the `plan.md` section; Stop; OpenPR |
| m1 | The lock's overlap rule | deferred | radius syntax restricted (§5 `chain.py`); the lock itself is deferred |
| m2 | herdr's `unknown` state; folder trust | taken | §8; #215 |
| m3 | A stale tick lock; dispatch order | taken | §8 |
| m4 | Stale on #213 | fixed | §3, read at 4296edc |
| m5 | The doc test runs one way | taken | #217 |
| m6 | `run` is not started once | changed | `run` never exits on its own, so nothing restarts it; R2 |
| m7 | No migration for v1 chains | changed | §5 `routing.py`: two tables |
| m8 | No path for an existing issue | taken | `feature new --issue` |

The re-check:

| Id | Finding | How | Where it is settled |
| --- | --- | --- | --- |
| X1 | Phase 1 depended on S4 and S5; S5 needed state | changed | every dependency it names holds in GitHub's graph, directly or transitively (§10), but its linear order is not kept; v1 routing kept (§5) |
| X2 | The Designer is an unjudged writer | taken | §4.4 own worktree; §4.5 the acceptance record |
| X3 | Finished means idle, not stopped | taken | §4.2 stop first; §6 proof in throwaway worktrees; §4.3 `assert_untouched` |
| X4 | The `.claude` check fires on Claude Code's own writes | taken | §7 `hooks_disabled` parses the files |
| X5 | Radius on `base...HEAD` was half-taken | taken | §7, at accept and OpenPR |
| X6 | Writes outside the worktree go unjudged | taken | §4.2 fingerprint; §4.7 hooks off; base SHA at accept |
| X7 | S3 silently reverted #206 | taken | §5 `hooks.py`; #207 |
| X8 | "Red" was ill-defined | taken | §6, the red test, precisely |
| a | The v1 test matched every new chain | taken | `chain: 2` |
| b | `plan.md` was not bound to the submission | taken | `plan.commit` |
| c | The Reviewer's snapshot predated `proof.md` | changed | snapshot at `proof.md`'s commit; a review is current only for that commit (§6 `review.md`) |
| d | Glob-against-glob overlap | taken | radius syntax restricted |
| e | `test` in the models table | taken | §5 `models.py` |
| f | Pre-commit on the loop's commit | taken | §4.2 and §4.7 |
| g | Count stale | fixed | §3 |
| h | Stale gate code in a long-lived `run` | taken | §8 re-exec; the heartbeat |
| i | A `.claude/**` radius | taken | §7's last row |
