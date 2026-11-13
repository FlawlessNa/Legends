# Working a ticket

## Before you start

1. **Read the ticket, then its epic's intent in full.** The intent says why,
   which is what keeps technically correct work from being unwanted work.
2. **Read the spec sections the ticket names.** If the ticket is ambiguous,
   read more of the spec before you ask.
3. **No epic?** A standalone `ready-for-agent` ticket carries its own intent:
   say in a line what you will change, and go. A request with no ticket and no
   agreed intent is a topic: see `topics.md`.
4. **List the ticket's `## Constraints`.** Each one must still hold when you
   are done, even where the acceptance criteria would be easier to meet by
   breaking it. Your PR ticks them one by one, and the reviewer checks each
   (`code-review.md`). If meeting the ticket seems to need breaking one, stop
   and ask.

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
   then posts one comment that starts with its verdict. If the main Claude
   account returns no verdict (for example it is out of usage), the review
   runs once more on a fallback account, when one is configured.
2. **On approve,** the workflow merges exactly the reviewed commit. It
   squash-merges, unless a commit in the PR has more than one parent (it brings
   `dev` in): then it merge-commits, so the epic keeps `dev`'s history.
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

CI (`.github/workflows/ci.yml`, the `gates` check) runs ruff and pyright on the
Python files your PR changes, and the whole default `pytest`, on every PR into
`dev` or an `epic/**` branch. A red `gates` is yours, as a red local run is.

`testing.md` has the procedures; `typing.md` covers the pre-commit gates. The
import direction in `AGENTS.md` ("The repo") is a test,
`tests/test_layering.py`: fix a violation by moving the code, never by adding
an exception.

### Against the live game

**A change that could alter which keys reach the game, or when, says in its PR
how it was verified against the live game, or why it was not.** That covers the
input send path, Movement compilation, timing, focus, and any DecisionMaker
whose Actions change. `game-client.md` has the two tools: the probe, for what
is on screen with no Session running, and a Test Session that the maintainer
starts and you read with the Session reader.

- **Verified:** write the expectation in the PR before the run, then the
  verdict with counts and the Session directory (`game-client.md`, "Live
  Session").
- **Not verified:** say why (no client open, the maintainer was not available
  to start a Session, the change needs a Trial run at the client), and put what a human
  must watch in the PR's handoff. That is a legitimate outcome, not a failure;
  "Nothing to verify" is not one when keys or timing can change.

## When to stop and hand back

Stop rather than finish whenever the work needs:

- a **measured constant**: anything timed, tuned or read off a running client.
  These are Expectations (`CONTEXT.md`);
- a **running game client**, to reproduce, confirm or record, beyond the
  probe and a Test Session the maintainer starts for you ("Against the live
  game" above);
- a **Trial run**: a Trial schedule (`configs/trials/`) driven at the client,
  which the maintainer starts;
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
- what is left of `configs/maps/` (retired by #399, ADR 0004), and pinned
  dependency versions;
- `maple/decision_makers/inventory_manager.py`, which is parked (see
  `maple/AGENTS.md`).

## Handing over

The PR body is the handoff, shaped by `.github/PULL_REQUEST_TEMPLATE.md`. It
covers:

- what changed;
- the test that was red without the change;
- each of the ticket's constraints, ticked, with how it holds;
- how the change was verified against the live game, or why not, when it could
  alter which keys reach the game or when (above);
- **what you could not verify**;
- the ADRs and invariant ids the change bears on;
- what a human still has to do.

Reviewing is a different job: see `code-review.md`.
