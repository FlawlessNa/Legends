# Working a ticket

## Before you start

1. **Read the ticket, then its epic's intent in full.** The intent says why,
   which is what keeps technically correct work from being unwanted work.
2. **Read the spec sections the ticket names.** If the ticket is ambiguous,
   read more of the spec before you ask.
3. **No epic?** A standalone `ready-for-agent` ticket carries its own intent:
   say in a line what you will change, and go. A request with no ticket and no
   agreed intent is a topic: see `topics.md`.

**Stop and ask instead of guessing** when the work shows the intent is wrong,
ambiguous or silent on something that matters, or when the ticket crosses the
spec threshold (`topics.md`) and no spec covers it.

## Branch and PR

- **Standalone ticket:** branch off `dev`, and open the PR into it. The
  maintainer reviews and merges it.
- **Ticket of an epic:** branch off `epic/<slug>`, and open the PR into it. Say
  `Closes #<ticket>` in the body.
- **You never merge anything.** A separate worktree is optional; it is useful
  when several sessions work in parallel.

### The epic flow

A PR into `epic/**` is reviewed and merged without the maintainer
(`.github/workflows/claude-review.yml`):

1. Claude reviews it against the ticket, the epic's intent, and this file,
   then posts one comment that starts with its verdict.
2. **On approve,** the workflow squash-merges exactly the reviewed commit.
3. **On request-changes,** the `review` check fails. Read the comment, fix
   every blocking finding, and push. The push triggers a fresh review.
   If you disagree with a finding, say so in the PR and stop: the maintainer
   decides.

The `epic/**` ruleset requires a PR and a passing `review` check, so nothing
reaches an epic branch any other way. When every ticket is merged, open one PR
from `epic/<slug>` into `dev`, which the maintainer reviews against the spec's
acceptance criteria.

Every review draws on the maintainer's usage limits, so push a PR when it is
ready, not to see what the reviewer says.

## Proving it

```
pytest        ->  0 failed, 0 errors, 0 xfailed
```

That is the green baseline, from the repo root with no flags. **Any `failed`
or `error` line is yours.** The passing and deselected counts move as tests
are added. What must hold is the shape: nothing failed, no xfails, and every
deselected test accounted for by an opt-in marker (`live`, `system`, `lab`,
`client_files`, `frames`).

- **A behaviour change lands with a test that fails without it.** Stash the
  source change, keep the test, run it, and confirm it goes red for the reason
  you expect.
- **A refactor adds no test, and passes the existing suite untouched.** If you
  had to edit a test, it was not a refactor: say what behaviour moved.
- **A red `lab` test is not a broken build.** `lab` tests measure rather than
  gate. Never mark a test `lab` to make it stop failing.
- **Green means the Invariants hold, not that the bot works.** Nothing in the
  default suite drives a game client.

`testing.md` has the procedures; `typing.md` covers the pre-commit gates.

## When to stop and hand back

Stop rather than finish whenever the work needs:

- a **measured constant**: anything timed, tuned or read off a running client.
  These are Expectations (`CONTEXT.md`);
- a **running game client**, to reproduce, confirm or record;
- a **minimap trail**, recorded through the GUI editor in
  `maple/model/mechanics/minimap_creation/`;
- a judgment that reduces to **watching the character**.

Stopping is compliance, not failure. Report what you finished, what you did
not, and what the human must do. Work that rests on an Expectation is
`ready-for-human` (`triage-labels.md`).

## What you may change

**Freely,** when tests cover it and no ADR governs it: tests, docs, telemetry
Event Types (additive only), and offline logic — compilation, pathfinding,
config parsing, logging.

**Not without asking**, because the tests will not catch you being wrong:

- the input send path, focus handling, and the Held-Keys Ledger (ADR 0002);
- the telemetry envelope and transport (ADR 0001);
- anything an ADR decides;
- map JSON under `configs/maps/`, and pinned dependency versions;
- `maple/decision_makers/inventory_manager.py`, which is parked (see
  `maple/AGENTS.md`).

## Handing over

The PR body is the handoff, shaped by `.github/PULL_REQUEST_TEMPLATE.md`. It
covers:

- what changed;
- the test that was red without the change;
- **what you could not verify**;
- the ADRs and invariant ids the change bears on;
- what a human still has to do.

Reviewing is a different job: see `code-review.md`.
