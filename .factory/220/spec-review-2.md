---
ticket: 220
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "start is idempotent by name, on FakeLauncher and on the herdr adapter, so a second start on the same launcher with a name already started returns a Handle equal to the first and starts no second worker, and a herdr adapter whose agent get finds the name issues no pane split, agent start, agent prompt or send-keys and returns a Handle with that agent's pane id whose prompt is marked as not seen to start"
---

# Spec review, cycle 2: the launcher, with herdr behind it

**Verdict: `pass`.** I checked only the seven findings from `spec-review.md`,
against `spec.md` at `d3e57fd`. All seven are resolved. The spec now has 25
criteria. Its closing table maps each finding to criteria, and I checked that
each number in the table points at the right criterion.

Four notes remain, listed at the end. None changes a criterion. Each can be
handled in the plan or the PR body.

## 1. Credentials: resolved

Criterion 3 now lists eight variables:

- `GH_TOKEN=factory-worker-has-no-credentials`;
- `GH_CONFIG_DIR`;
- `GITHUB_TOKEN=`, `GIT_ASKPASS=` and `GIT_TERMINAL_PROMPT=0`;
- the three `GIT_CONFIG_*` variables.

Criteria 5 and 6 follow the new count. I re-probed the exact set in my
scratchpad:

- **gh.** `GH_TOKEN=factory-worker-has-no-credentials GITHUB_TOKEN= GH_CONFIG_DIR=<empty dir> gh auth token`
  printed the sentinel, not the keyring token. The directory stayed empty.
- **git.** I set `SSH_ASKPASS` to a script that returns a password, and the
  marker helpers in `GIT_CONFIG_SYSTEM` and `GIT_CONFIG_GLOBAL` as in cycle 1.
  `git credential fill` ran no helper and never called the script. It failed
  with "terminal prompts disabled". In cycle 1 I showed the same result with
  `core.askPass` set. An empty `GIT_ASKPASS` is non-null, so git skips both
  fallbacks.

*Decisions* records the departure from the issue's literal `GH_TOKEN=`, and
why. *Could not verify* now carries the empty-`--env` item and its
consequence: every git command fails if `GIT_CONFIG_VALUE_0` is dropped.

## 2. Leaked panes: resolved

Criterion 14 makes every error after a successful split carry the Handle. It
names a test for each case I listed:

- `agent_not_found` after the trust answer;
- an `agent start` that times out or returns any other code;
- a state other than `blocked` after `agent_not_ready`;
- an `agent prompt` that stalls, times out or fails.

Every wait now has a timeout:

- `agent start --timeout` (criterion 11);
- `agent wait --timeout` (criterion 12);
- `agent prompt --timeout` (criterion 11);
- `stop`'s own timeout (criterion 19).

## 3. Trust dialog: resolved

- **Layout.** Criterion 12 answers only when the screen shows "No, exit" as
  option n, followed by an option n+1 starting "Yes", with only whitespace
  between them. That is the one layout in which `down enter` selects Yes.
  The screen is read with `--source recent-unwrapped` and whitespace is
  collapsed, so a wrapped question still matches. A cursor marker on the Yes
  option disqualifies the screen, which is right: there, Yes is already the
  default and `down` would move past it.
- **Worktree check.** Criterion 13:
  - resolves a relative gitdir;
  - requires the gitdir to be a direct child of `<common>/worktrees`;
  - requires that child's `gitdir` file to point back at `cwd/.git`;
  - tests a relative gitdir, a gitdir outside `worktrees`, and a missing or
    mismatched back-pointer.

  See note a.

## 4. Prompt race: resolved

Criterion 11 pins
`agent prompt <pane> <prompt> --wait --until working --until blocked --timeout`,
with no `--`. Criteria 1 and 9 add a "seen to start" flag to the Handle. For a
Handle without it, `idle` and `done` map to `blocked`, never to `finished`.

The crash-replay consequence is stated: a replay costs one attempt.

## 5. `stop`: resolved

- **No vacuous pass.** Criterion 19 raises before closing anything unless
  `shell_pid` is reported and is present in the snapshot taken before the
  close. It names the empty-table test.
- **A pane already gone.** Criterion 18 treats `pane_not_found` as already
  stopped, and repeats that on a second `stop`. This agrees with criterion 20:
  `agent get` on a closed pane id returns `agent_not_found`, which reads as
  `gone`.
- **What the snapshot cannot see.** Orphaned processes, and a pane already
  gone at `stop`, are both under *Could not verify*. That includes the honest
  narrowing of "the process tree is gone" to the tree the snapshot shows.

## 6. Pinned behaviours: resolved

- **Pane id everywhere.** Criterion 9 targets the pane id, never the name.
  Criterion 11 makes every agent command after `agent start` target the pane
  id too.
- **`stop` raises.** Criterion 16 raises, with no herdr command, for a
  designer Handle and for `HERDR_PANE_ID`.

## 7. Packaging: resolved

The edit is now a maintainer action, with the exact line:
`packages = ["factory", "factory.launchers"]`. Criterion 24 adds
`pyproject.toml` to the files this ticket leaves unchanged.

## Notes, not findings

**a. Compare the back-pointer as resolved paths, never as strings.** On this
machine, `.git/worktrees/issue-220-launcher/gitdir` reads
`C:/Users/Nassim/.herdr/worktrees/Legends/issue-220-launcher/.git`, with
forward slashes. A string comparison against a Windows `Path` never matches,
so every trust dialog would be refused. That fails closed, but it fails
silently. The plan should include a test whose back-pointer uses forward
slashes, as git writes it.

**b. Criterion 8 needs a per-launcher record of started workers.** This is the
criterion quoted above. Its two clauses agree only if the adapter remembers
the Handles it started in this process, and checks that record before calling
`agent get`:

- on the same launcher, the second `start` must return a Handle equal to the
  first, so "seen to start" is true;
- on a fresh launcher, `agent get` finds the name, so the flag is false.

An adapter that always calls `agent get` fails the first clause. The criterion
is decidable as written. The plan should name the record.

**c. Targeting a pane id during a blocked startup is unverified.** herdr's
skill says `agent_not_ready` "keeps the name available for `agent read` and
`agent send-keys`". It does not say the same of the pane id, which is what
criterion 11 now uses. If herdr does not resolve the pane id there, the read
returns `agent_not_found`. Criterion 14 then raises with the Handle, which
fails closed. Add this to *Could not verify*.

**d. The likely real layout is refused.** If the live dialog lists "Yes"
before "No, exit", as its default of "No, exit" suggests, criterion 12 sends
nothing. Every first dispatch into a fresh worktree then fails, and that
includes every judge snapshot. *Could not verify* says this. The PR should
also list it under what a human still has to do: capture the dialog once,
with `agent read --source recent-unwrapped`, before the dry run (#223).

## What this review could not verify

- The trust dialog's real layout, and whether herdr resolves a pane id for an
  agent blocked at startup.
- Whether herdr passes an empty `--env` value through.
- I did not run pytest, because no source changed.
