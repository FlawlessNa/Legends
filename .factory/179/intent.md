---
ticket: 179
stage: plan
accepted_by: nassim
accepted_at: 2026-10-15
---

# Intent: the factory's process belongs in the repo

## Problem statement

The factory's design exists in one Claude doc and in forty-one issue bodies.
Neither is in the repo, neither is versioned with the code, and neither is
loaded by anything. A fresh agent picking up a ticket today reads `AGENTS.md`,
sees no mention of a factory, and writes code.

Nassim's words: *"factory isn't documented in-repo, and nothing enforces you to
follow the factory standards, not even instructions-only, right now. So any
fresh agent working on a ticket is likely to simply skip everything."*

## Proposed outcome

`docs/factory/` holds the canonical process, versioned with the code. A fresh
session with no conversation history can read it and work a ticket correctly.
Where it and the Claude doc disagree, the repo wins.

## Affected users and systems

- Every agent that works a ticket in this repo, including interactive sessions.
- `AGENTS.md`, which must point at it, since that is the one file always loaded.
- #153 (the entry skill), which routes to these documents rather than restating
  them.
- #189 (bootstrap enforcement), whose hooks enforce what these documents state.
- #139 (the artifact chain), which implements in code the contract this ticket
  settles in prose.

## Constraints

- The working model is a fresh session per ticket: no conversation history,
  nothing but the repo and the artifact chain. If a fresh session cannot work a
  ticket from these documents plus the chain, the documents are inadequate.
- It must not restate what `AGENTS.md`, `CONTEXT.md` or the ADRs already say.
  Duplication is how documents drift apart.
- It describes a process that does not exist yet. Every rule must be honest
  about whether it is enforced mechanically, by instruction, or not at all.

## Open questions

- Does `docs/agents/triage-labels.md` survive, or fold into this? (#187)
- Where does the Document stage sit? Recorded as stage 8 per Nassim; #186 holds
  the argument for moving it before Review.
