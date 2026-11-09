<!--
This template is the handoff. A reviewer -- human or agent -- reads it before the
diff, and it is the only place some of this information can come from.
Delete sections that genuinely don't apply; don't delete the "Could not verify"
one, which is the point of the template.
-->

## What this changes

<!-- One paragraph. What behaviour is different afterwards, not a list of files. -->

Closes #

## Proof

<!--
For a behaviour change, name the test that fails WITHOUT this diff, and what it
said before. Stash the source, run the test, paste the failure. See
docs/agents/testing.md, "Proving a new test earns its place".

For a refactor: say "Refactor -- no new test" and confirm every existing test
passes unmodified. If you edited a test, this is not a refactor; say what moved.
-->

- [ ] `pytest` is green: 0 failed, 0 errors, 0 xfailed, and every deselected
      test carries an opt-in marker
- [ ] `ruff check` clean on the files I touched

**Test that was red without this change:**

## Constraints

<!--
Copy every line of the ticket's `## Constraints` and tick each one, saying how
it holds. The reviewer checks the same list (docs/agents/code-review.md, check
2); a broken one blocks the PR whatever the tests say. If meeting the ticket
needed breaking one, you should have stopped and asked instead.
-->

- [ ]

## Verified against the game

<!--
REQUIRED when this change could alter which keys reach the game, or when:
the input send path, Movement compilation, timing, focus, or any
DecisionMaker whose Actions change. See docs/agents/tickets.md, "Against the
live game", and docs/agents/game-client.md for the tools.

Either: the expectation you wrote before the run, then the verdict with counts
and the Session directory (logs/<timestamp>/), or the probe command and PNG
path.
Or: why it was not verified, and what a human must watch (also under Handoff).

Write "Not applicable -- no change to which keys reach the game, or when" only
if that is true, and say why in a line.
-->

## Could not verify

<!--
REQUIRED. The suite proves Invariants; it cannot prove Expectations, and no test
carries the `live` marker today, so nothing here is checked against a running
client. Say what a human would have to watch to know this is right.

Write "Nothing -- fully covered offline" only if that is actually true. It is
true for pure logic under test; it is rarely true for anything touching input,
timing, focus, or detection.
-->

## Decisions and invariants touched

<!--
- ADRs this change interacts with, and whether it upholds or contradicts them.
  Contradicting one is allowed; doing it silently is not.
- Invariant ids from docs/planning/movement-invariant-catalogue.md (A1, D2, ...)
  that this change bears on. Note that A2 currently FAILS (#25) and A4 is
  UNSETTLED (#75) -- do not claim to have fixed either as a side effect.
- Vocabulary: if this introduces a domain concept, it should already be in
  CONTEXT.md, or it needs to be.
-->

## Handoff

<!--
Anything the next person -- reviewer, or whoever picks this up -- must do that
you could not. Recording a minimap trail, measuring a constant, watching a
rotation. If you stopped short of the ticket, say exactly where and why.
-->
