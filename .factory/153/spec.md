---
ticket: 153
stage: design
method: assent
criteria:
  - .claude/skills/factory/SKILL.md exists, carries skill front-matter with name and description, and tells the agent to run `factory next <ticket>` and follow the stage section it names
  - Because `factory next` does not exist, SKILL.md routes through a literal table computed from the .factory/<n>/ front-matter, and the table is marked in SKILL.md itself as a stub to be replaced by #140
  - Every row of that table names only a stage, a role and a section of docs/factory/stages.md; no sentence in SKILL.md describes how to perform any stage's work
  - Each of the ten stage sections in docs/factory/stages.md has exactly the seven slots, as headings in this order -- Trigger, Entry gate, Context, The work, The oracle, Artifacts, Stop and hand back -- so stages.md contains seventy slot headings
  - Every enforcement marker and issue reference already in docs/factory/stages.md survives the reshaping
  - No slot restates AGENTS.md, CONTEXT.md, an ADR or another docs/factory/ page; each cross-references it
  - docs/factory/stage-template.md exists with the seven slot headings and placeholder prompts, and nothing stage-specific
  - "`git check-ignore .claude/settings.local.json` exits 0, and `git check-ignore .claude/settings.json .claude/skills/factory/SKILL.md` exits 1"
  - .claude/settings.json and .claude/skills/factory/SKILL.md are tracked in git; .claude/settings.local.json is not
  - The PR body states that the routing table is a stub to be replaced by #140
  - The suite passes unchanged
specified_by: claude
specified_at: 2026-10-16
reviewed_by: null
---

# Spec: one entry skill that routes, plus per-stage instruction slots

## Source

Issue #153, body as rewritten 2026-10-15. Its "Acceptance" list is the source;
the criteria above transcribe it into checkable form. The issue is
authoritative if they diverge. The comments are superseded by the body and are
not a source.

## Requirements

1. **The router.** `.claude/skills/factory/SKILL.md` runs `factory next`, reads
   the section it names, and follows it. It does not choose a stage, and it does
   not proceed past a non-zero exit code.
2. **The stub.** Until #140, the stage is computed by hand from the chain's
   front-matter using a table in the skill. Each row: a condition on the
   artifacts, the stage, the role, the section. The first matching row wins, so
   two readers of the same chain reach the same row.
3. **The seven slots** per stage in `stages.md`: Trigger, Entry gate, Context,
   The work, The oracle, Artifacts, Stop and hand back. The work ends at an
   artifact, never at a merge.
4. **The template** for adding a stage: the same seven headings, blank.
5. **Tracking `.claude/`**: the bare `.claude` ignore becomes
   `.claude/settings.local.json`; `.claude/skills/` and `.claude/settings.json`
   are tracked.

## Verification method: assent

Only criteria 8, 9 and the slot count are checkable by a command. Whether
the stage text is right, and whether the skill has stayed a pointer rather than
a paraphrase, is settled by Nassim reading it. `method: suite` would be a lie.

## Known gap in this spec

`specified_by` and the Builder are the same agent (#180), and `reviewed_by` is
`null`. By `artifacts.md`, a `null` here blocks stage 3. This ticket proceeds
anyway, as #179 and #191 did, under the bootstrap sequence. The routing table
this ticket writes would send it back to stage 2. That disagreement is recorded
here, not resolved.
