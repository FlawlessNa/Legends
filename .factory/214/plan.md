---
ticket: 214
stage: build
radius:
  - docs/factory/design.md
  - docs/factory/README.md
  - docs/factory/stages.md
  - docs/factory/roles.md
  - docs/factory/artifacts.md
  - docs/factory/bootstrap.md
  - CONTEXT.md
  - .factory/214/**
tasks: null
merge_order: null
proof:
  red_test: none
  red_output_sha: none
  suite: pass
docs_cleared: []
---

# Plan: commit the agreed factory design

## Radius

These are exactly the files spec criterion 16 allows.

| Path | Why |
| --- | --- |
| `docs/factory/design.md` | New. The design, with the re-check folded in per the fold table. |
| `docs/factory/README.md` | One entry in "## The rest". The link to `merge-policy.md` is kept, because `test_the_factory_readme_links_the_policy` reads it. |
| `docs/factory/stages.md`, `roles.md`, `artifacts.md`, `bootstrap.md` | A Supersedes note after the H1. In `artifacts.md`, "the Foreman (#159)" becomes "the factory loop (#159)". Nothing is renumbered, because `hooks.py:124` and `:134` cite `bootstrap.md` rule 3 and `stages.md` stage 2. |
| `CONTEXT.md` | A new `## The factory` section: a scoping preamble, then Factory loop and Orchestrator. |

**Not in the radius:**
- `merge-policy.md` and `stage-template.md`, which belong to #217;
- `factory/models.py` and `configs/factory-models.toml`, where Foreman is retired by #218;
- any source file.

## Order of work

1. Port the design to markdown in the scratchpad, and verify every code citation at `4296edc` before it enters the tree. Done: all cited lines were re-read in this worktree.
2. Apply every edit through one script, so the changes outside `design.md` are exactly the notes, the one-line Foreman fix, the README entry and the `CONTEXT.md` section.
3. Run the mechanical checks against the criteria:
   - `grep -ni engine docs/factory/design.md` returns nothing;
   - `grep -rni foreman docs/factory/` returns nothing;
   - `git diff --stat` touches only the radius;
   - the `design.md` headings run from 0 to 13.
4. Run `pytest` from the worktree root and record the shape.
5. A separate session reviews the diff against the spec, and writes `review.md`.

## Proof

This is an assent ticket. No behaviour changes, so there is no red test (`red_test: none`). The proof is the green suite and a review of the diff against the spec. `suite` is filled once the suite has run.

## Spec review history

Three cycles:
- `spec-review.md`: changes-requested, 13 findings;
- `spec-review-2.md`: changes-requested, 4 findings;
- `spec-review-3.md`: pass.

Under the design's own cap (R4: 2 cycles per judged stage), a v2 ticket would have parked after cycle 2. This one is v1 and worked by hand, so the cap does not apply. It is recorded here because it is exactly the case the cap exists for, and the third cycle was a narrow confirmation, not a new review.

## Could not verify

- That the re-check text in the spec is verbatim. It was transcribed from the report as relayed in-session, and no file holds the original.
- That a reader without the `.lavish/` sources can follow every cross-reference. Ticket bodies and `design.md` cite each other, and this was checked by reading, not by a tool.

## Proof, recorded

`pytest` from the worktree root at the build commit: `1197 passed, 3 skipped, 25 deselected in 60.94s`. 0 failed, 0 errors, 0 xfailed. The deselected tests are the opt-in markers.

Mechanical checks:
- `grep -ni engine docs/factory/design.md`: no lines.
- `grep -rni foreman docs/factory/`: no lines.
- `design.md` headings run from 0 to 13.
- `git status` touched only the radius.
