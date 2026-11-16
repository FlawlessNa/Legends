# Reviewing a change

Written for whoever reviews a diff here, human or agent. Its purpose is to make
the review catch what the author structurally could not.

## Read different things than the author did

An agent that reviews a change by re-reading `AGENTS.md` and the diff mostly
agrees with itself: it shares the author's inputs, so it shares the author's
blind spots. A review is worth something when it is grounded in sources the
author may never have opened.

Read, in this order:

1. **The PR body**, before the diff — specifically its *Could not verify* section.
2. **The ticket**, and its map's *Answer records* if it has one. That is the
   acceptance criteria the change is actually accountable to, and its
   `## Constraints` list, which check 2 ticks. `gh issue view <n> --comments`.
3. **`docs/adr/`** — every ADR touching the area, whether or not the PR mentions
   one.
4. **`docs/planning/movement-invariant-catalogue.md`** for anything touching
   movement compilation or input. Entries have stable ids; cite them.
5. **`CONTEXT.md`** for the vocabulary the change should be using.

Read the diff last. By then you know what it was supposed to do.

## The six checks

### 1. Does the "Could not verify" list match the risk of the diff?

**This is the job.** The suite proves Invariants and nothing else. No test carries
the `live` marker, so nothing here is checked against a running client.

An author who writes "Nothing — fully covered offline" on a diff that changes when
keys are sent is either wrong or has not thought about it. Push back. The correct
outcome of a review is often "this is fine, and here is what a human still has to
watch" — not an approval that pretends the gap isn't there.

Conversely, an over-long unverified list on a pure-logic change is a signal the
author didn't understand their own diff.

A diff that could alter which keys reach the game, or when, must say how it was
verified against the live game (the probe or a Test Session, `game-client.md`)
or why it was not (`tickets.md`, "Against the live game"). A PR that says
neither is a blocking finding. A verdict that reports a Session must give the
expectation, the counts and the Session directory; one without them is a claim,
not a verification.

### 2. Does every constraint of the ticket still hold?

List the ticket's `## Constraints` (and any constraint its spec sections state
for it), and tick each one against the diff: **holds**, or **broken** with the
file and line. Do this even when every acceptance criterion is met: the
expensive failures here meet the ticket's goal by quietly breaking one of its
constraints, as when a change to pathfinding changed the unit Position is kept
in, against a ticket that said it must not. Tests rarely catch that, because the
author updates them along with the code.

A broken constraint is a blocking finding on its own, whatever the tests say.
If the ticket has no `## Constraints` section, say so in the review and check
the "not without asking" list in `tickets.md` instead.

### 3. Did the test actually fail without the change?

The author is asked to demonstrate this (`docs/agents/testing.md`). You can check
it: stash the source paths, keep the test, run it. A test that passes on the base
commit is not testing the change, however good it looks.

Watch for the failure mode this repo has already produced twice: a test whose
assertion sits outside its loop (`test_read_text`), and tests written as
`pytest.fail()` placeholders that were never filled in (`test_controller.py`).
Both looked like coverage in the tree.

### 4. Which invariants does the diff bear on?

Name them by id. Then check the catalogue's **Status** column before reporting
anything:

- **A2 Terminal Release** — currently *fails*, tracked by #25.
- **A4 Skill Key Closure** — *unsettled*, pending #75.
- **D1 Cancel Safety** — currently *fails*, tracked by #26.
- **B1 Truncation Integrity** — *not yet checkable*.
- **B3 Distance Fidelity** — an Expectation, needs #13/#14.

Reporting a known-broken invariant as a new finding wastes everyone's time. So
does an author claiming to have fixed one as a side effect — if A2 or D1 is now
satisfied, that is a ticket closing, with its own evidence.

### 5. Does it contradict a decision?

ADRs record what was chosen *and what was rejected and why*. A change that
quietly reintroduces a rejected alternative is the most expensive thing to catch
late, and the diff alone never shows it — ADR 0002 rejected a dispatch-time
corrective prefix and pushing ledger state to DecisionMakers, and both look
perfectly reasonable in isolation.

Contradicting an ADR is allowed. Doing it without saying so is not. If the change
supersedes a decision, the ADR needs updating in the same PR.

The import direction (`maple` imports `botting`, never the reverse, and the rest
of `AGENTS.md`, "The repo") is a test, `tests/test_layering.py`. A diff that adds
an entry to its `KNOWN_EXCEPTIONS` is a finding: the rule is that a violation
is fixed by moving code.

### 6. Is it speaking the project's language?

New names go through `CONTEXT.md`. If the diff introduces a domain concept the
glossary doesn't have, either the glossary is missing an entry or the author
invented a synonym for something that already has a name — the entries list the
synonyms they reject, so this is checkable rather than a matter of taste.

## What not to do

- **Don't re-derive the implementation.** If it passes, upholds the invariants,
  and the unverified list is honest, the design is the ticket's business, not the
  review's.
- **Don't report style.** `ruff` owns that, and once #76 lands it owns it in a
  hook. A review finding that a formatter would fix is noise.
- **Don't approve to be agreeable.** An unsupervised pipeline where every review
  passes is a pipeline with no review in it. "No findings" is a legitimate
  verdict; it is only worth something if the alternative was live.

## What a review outputs

- The ticket's constraints, each ticked **holds** or **broken** (check 2).
- Findings, most severe first, each anchored to a file and line.
- An explicit verdict on the *Could not verify* section: **accurate**,
  **understated** (and what is missing), or **overstated**.
- What a human must still do before this is trusted in a running Session.

That last line is what makes a review handoff-able. The next agent in the chain
reads it and knows whether the work is finished or merely correct.
