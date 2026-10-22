---
ticket: 214
stage: design
method: assent
criteria:
  - docs/factory/design.md exists and keeps the source's section numbering, 0 to 13, so tickets citing design.md §n resolve
  - every re-check finding X1 to X8 and a to i is folded into the section it changes, and section 13 maps each to where it now lives
  - section 0 records all eleven rulings as decided on 2026-10-22, with R1 as amended (the maintainer reads the spec, never the plan)
  - section 10 is the roadmap as ticketed, with real issue numbers and the blocked-by order that GitHub holds
  - every statement about current code is true at 4296edc, each with a file and line or a named function
  - the factory's orchestrating program is called the factory loop, never the engine, because Engine is the bot's process in CONTEXT.md
  - CONTEXT.md gains a factory loop entry that rejects Foreman and engine as synonyms
  - Foreman appears nowhere in docs/factory/
  - stages.md, roles.md, artifacts.md and bootstrap.md each open with a Supersedes note naming what design.md replaces, and nothing else in them changes
  - README.md links design.md from its index
  - no file outside docs/factory/, CONTEXT.md and .factory/214/ changes
specified_by: claude
specified_at: 2026-10-22
---

# Spec: commit the agreed factory design

## Source

Issue #214, and the design as accepted on 2026-10-22: `.lavish/factory-design.html`
in the maintainer's checkout, with the R1 amendment. The re-check's findings
X1–X8 and a–i are folded into the sections they change. The re-check is the
second independent review: verdict "ready after named fixes", relayed in the
session that produced the roadmap.

## What "folded in" means

The design is the authority, so it must not contradict itself. An amendment
changes the sentence it corrects, wherever that sentence is. It is never
appended as a later section that overrides an earlier one. Section 13, the
finding ledger, is where a reviewer looks up where each finding went.

## Naming

`CONTEXT.md` defines a Session as spawning "the `Engine`", and the bot's
documentation uses Engine for that process throughout. The factory's program
therefore needs another name. **The factory loop** is plain and descriptive,
and `factory run` is its command. Its module is `factory/loop.py`. Issue bodies
were already updated to match on 2026-10-22.

## Verification method: assent

The proof is a diff a reader can check against the source document and against
the code at `4296edc`. The suite must stay green, since `test_merge.py` reads
`merge-policy.md` and other tests may read `docs/`. No test is added, because
no behaviour changes.

## Not in scope

- Rewriting `stages.md`, `roles.md`, `artifacts.md` or `bootstrap.md`. Each
  roadmap ticket updates the part it changes.
- `merge-policy.md`'s errors, which belong to #217.
- Any change to `.lavish/`, which stays gitignored history.
