---
ticket: 179
stage: design
method: assent
criteria:
  - docs/factory/ exists and documents the stages, the roles, the artifact chain and its front-matter contracts, the exit-code contract, and the bootstrap rules
  - every rule states whether it is enforced mechanically, by instruction, or not at all
  - AGENTS.md points at it, in the always-loaded section
  - no rule is restated from AGENTS.md, CONTEXT.md or an ADR; each is stated once and cross-referenced
  - the artifact-chain contract is complete enough for #139 to implement a parser against it without further decisions
  - this ticket's own .factory/179/ chain is a worked example of the contract it defines
specified_by: claude
specified_at: 2026-10-15
reviewed_by: null
---

# Spec: docs/factory/

## Source

Acceptance criteria are those on issue #179, amended by Nassim. This file
transcribes them; the issue is authoritative if they diverge.

## Requirements

The documentation covers, each stated once:

1. **The stages** -- the ten-stage list, what each consumes and produces, and
   the gate that must pass before the next may start.
2. **The roles** -- who performs each stage, what each may write, what each may
   never touch, and when each escalates.
3. **The artifact chain** -- the `.factory/<n>/` layout, the front-matter
   contract per file, and the rule that tasks nest inside a ticket and never
   get chains of their own.
4. **The exit-code contract** -- cross-referenced to `factory/AGENTS.md`, not
   restated.
5. **The bootstrap rules** -- hand-enforcement precedes tool-enforcement; a
   command may not gate its own construction; artifacts from day one; a change
   that adds a commitment adds an issue.

## Verification method: assent

Nothing here is settled by a test. It is settled by Nassim agreeing the
documents say what the process is. `method: suite` would be a lie.

## Known gap in this spec

`specified_by` and the Builder are the same agent. That is the
separation-of-powers hole at the centre of the design, recorded here rather
than hidden: these criteria were not written by someone other than the agent
that will satisfy them. #180 is the fix. Until it lands, Nassim amending the
issue's acceptance is the only thing standing in for it -- and he did amend
#139's, which is the precedent.
