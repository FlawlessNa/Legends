---
ticket: 153
stage: plan
accepted_by: nassim
accepted_at: 2026-10-15
---

# Intent: one entry skill that routes, and stage text with one home

## Problem statement

An interactive session on a ticket branch has nothing that injects the stage
it is in. It reads `AGENTS.md`, is told to read `docs/factory/`, and from there
decides for itself what to do next. Two sessions on the same ticket can decide
differently, which is the randomness the factory exists to remove.

The obvious fix -- one skill per stage -- makes it worse: the model then
*chooses* which skill to load. And a skill that restates a stage is a second
source of truth with nothing keeping it in step with `docs/factory/stages.md`.

`stages.md` itself covers roughly half of what an agent needs per stage, so even
an agent routed to the right section would have to improvise the rest.

Separately, `.gitignore` ignores `.claude` wholesale, so any skill written there
exists on one machine only.

The ticket body, in Nassim's words: *"Instructions have one home. Everything
else is a pointer."*

## Proposed outcome

- `docs/factory/stages.md` is the only place stage instructions live, and every
  stage section has the same seven slots.
- `.claude/skills/factory/SKILL.md` is a router: it computes the stage, names
  the section, and says to follow it. It contains no instructions of its own.
- `.claude/skills/` and `.claude/settings.json` are tracked; only
  `.claude/settings.local.json` stays ignored.

## Affected users and systems

- Every interactive session on an `issue/<n>-*` branch.
- #140 (`factory next`), which replaces the skill's stub routing table.
- #163 (Foreman-spawned role agents), the second caller of the same stage text.
- #189 (bootstrap enforcement), which fills `.claude/settings.json` and needs
  `.claude/` tracked first.
- #186 (Document stage position), which edits the stage list this ticket
  reshapes.

## Constraints

- No instruction text outside `stages.md`. A pointer that paraphrases is a copy.
- No restating `AGENTS.md`, `CONTEXT.md`, an ADR or another `docs/factory/` page;
  reference them.
- `factory next` does not exist. The routing is stubbed as a literal table, and
  the stub must be visibly marked for replacement, not left.
- `settings.local.json` must stay ignored: it holds per-machine overrides.

## Open questions

- Acceptance is recorded from the maintainer having authored and rewritten the
  ticket body (2026-10-15) and approved the `.claude/` scope addition in a
  comment -- not from a signature on this file. The prompt handing over the
  ticket dated the rewrite 2026-10-16; the body's own note says 2026-10-15.
- How a stub can tell stage 4 from stage 5, and stage 8 from 9, from the
  artifacts alone. Settled in `spec.md` and flagged for #140.
