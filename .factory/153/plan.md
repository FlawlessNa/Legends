---
ticket: 153
stage: build
radius:
  - docs/factory/stages.md
  - docs/factory/stage-template.md
  - docs/factory/README.md
  - .claude/skills/factory/SKILL.md
  - .claude/settings.json
  - .gitignore
  - .factory/153/**
tasks: null
merge_order: null
proof:
  red_test: null
  red_output_sha: null
  suite: pass
docs_cleared: null
---

# Plan

## Files that change

- `docs/factory/stages.md` -- each of the ten sections reshaped into the seven
  slots. Existing text, markers and issue references kept; what was missing is
  filled by pointing at the page that already owns it.
- `docs/factory/stage-template.md` -- new, the blank seven-slot section.
- `docs/factory/README.md` -- one pointer to the template and the entry skill,
  so neither is discoverable only by `ls`.
- `.claude/skills/factory/SKILL.md` -- new, the router and its stub table.
- `.claude/settings.json` -- newly tracked, content unchanged (`{}`).
- `.gitignore` -- the bare `.claude` becomes `.claude/settings.local.json`.

No hard-stop path is in the radius: nothing under the input send path, focus
handling, the Held-Keys Ledger, telemetry, `configs/maps/`, pinned versions or
`inventory_manager.py`.

## Order

`stages.md` first, because the skill points at its section anchors and a
pointer must never be ahead of the thing it points at. Then the template,
extracted from the shape `stages.md` settled on. Then `.gitignore` and
`.claude/`, and the README pointer last.

## Risks

- **The skill turning into a paraphrase.** A routing row that says *how* rather
  than *where* is a second copy. Mitigated by the table having only condition,
  stage, role and section columns.
- **The stub outliving its purpose.** Marked in the skill as a stub for #140,
  and named in the PR body.
- **The stub computing stages the docs do not define.** Stage 4 vs 5 and 8 vs 9
  cannot be told apart from front-matter alone today; the stub's rows for them
  are a decision #140 should confirm or overturn, called out in the PR.
- **Un-ignoring `.claude/` exposes more than intended.** Today the directory
  holds only `settings.json`, `settings.local.json` and an empty `skills/`.
  Anything Claude Code later writes there unasked will show as untracked rather
  than be hidden -- which is the visible failure, not the silent one.
- **Restating `AGENTS.md`.** The stop-and-hand-back list and the green baseline
  are referenced, not copied.

## Proof of completion

No behaviour change and no new test: documentation and repo configuration.
`method: assent`. The mechanical criteria are checked by command and their
output pasted in the PR: `git check-ignore`, `git ls-files .claude`, and a count
of slot headings in `stages.md`. The suite must pass unchanged, which proves only
that nothing was broken.
