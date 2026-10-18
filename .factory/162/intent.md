---
ticket: 162
stage: plan
accepted_by: nassim
accepted_at: 2026-10-18
---

# Intent: the model is routed, never chosen

## Problem statement

Nothing decides which model runs a stage. Today a human picks a session's model
by hand, and once the Foreman (#159) starts sessions there will be nobody to
pick. The failure mode if the agent picks is known and one-directional: **an
agent asked to choose its own model chooses the strong one, every time.** It
costs nothing it can see and it is never the wrong answer from where it sits.

The inverse failure is worse and quieter. A table that routes a judgement stage
to a cheap model buys a bad spec, and a bad spec is paid for by every stage
downstream of it.

## Proposed outcome

A table, in config, that answers "which model runs this stage of this ticket"
and says why. The policy it encodes is the maintainer's, stated directly:
standard work on Sonnet, complex work on Fable falling back to Opus while Fable
is unavailable, Haiku reserved for trivial work and routed to by nothing.

The table routes to a **tier**, not to a model id, because the policy is
written in tiers and ids churn. Fable's absence is one line of config, so its
arrival is one line too.

## Affected users and systems

- #159, the Foreman, which is the only intended caller of the resolution.
- The maintainer, who owns the policy and must be able to change it without a
  code change — and who will want to know, after a bad result, which model
  produced it.
- `factory next` (#140), whose stage vocabulary this reuses rather than
  reinventing. A second spelling of the stage names would be a second thing to
  keep in step.

## Constraints

- **Pure and offline.** A function of the table, the stage and the ticket's
  front matter. No network, no probing of what the subscription actually has:
  availability is declared, not discovered, because a resolver that asks the
  network gives different answers on different days.
- **No new runtime dependency.** `factory` declares none on purpose, and
  pinning one is a maintainer decision (`AGENTS.md`).
- **A malformed table must fail loudly.** Silently falling back to the strong
  model turns a configuration error into a bill nobody is shown.
- This ticket does not start sessions and does not write artifacts. It answers
  a question; #159 acts on the answer.

## Open questions

- **Concrete model ids are not verifiable from here.** The table stores the
  aliases a harness accepts (`fable`, `opus`, `sonnet`, `haiku`) rather than
  ids like `claude-opus-5-5`. That is also the portable choice — collaborators
  run other harnesses — but it means this ticket cannot prove any id is real,
  and does not try to.
- Whether `plan` should be `standard` or `trivial` is a judgement recorded in
  the issue, not settled by measurement: drafting an `intent.md` decides what
  the ticket *is*, so it is `standard`.
