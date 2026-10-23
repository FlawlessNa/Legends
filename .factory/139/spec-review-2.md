---
ticket: 139
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "a top-level key followed by indented \"- item\" lines reads as a tuple of those items in order, each stripped of surrounding whitespace with quotes kept verbatim, and a list followed by a nested block or another key ends where it should"
---

# Spec review, cycle 2: chain v2

**Verdict: `pass`.** I checked only the eight findings in `spec-review.md`,
against `spec.md` at `8d7f260`. All eight are resolved. Three notes remain.
None blocks, and each can be settled in the plan or the tests.

## 1. The mapping rule: resolved

Criterion 3 and the Shape now define a mapping item as text after `- `
matching `^[A-Za-z_][A-Za-z0-9_]*:(\s|$)`. Prose that contains `: ` is read,
and has its own criterion and test.

I re-ran the scan over every committed front-matter block at `8d7f260`, with
the new rule and the "differing indentation" rule. No real list is unreadable,
including this spec's own `criteria` and `.factory/197/spec.md`.

## 2. Criterion 10: resolved

- **Pinned.** It names the thirteen tickets at `9654223`, so a future
  `chain: 2` chain cannot break it.
- **No longer vacuous.** "Parses" became a count of criteria against the raw
  `- ` lines, plus non-empty radii that pass `radius_errors`.
- **Blocked answers allowed.** The three blocked answers (153, 179, 191) are
  explicitly allowed.

## 3. `version`: resolved

There are now four cases: absent → 1, `1` → 1, `2` → 2, anything else raises
`UnknownChainVersion`. The Shape says `chain: 2  # x` raises, and justifies it.
That is decided and testable.

## 4. `blob`: resolved

- **The command.** It runs `rev-parse --verify --quiet <commit>:<relpath>^{blob}`.
  I confirmed in cycle 1 that this form returns nothing and exits non-zero for
  a directory.
- **The path.** It is a POSIX path relative to the repo root, run with `-C`.
- **The test.**
  - It sets `core.autocrlf=true` in the temporary repo itself.
  - It asserts the file on disk has CRLF.
  - It compares against `hash-object` of the LF content.

  That is the comparand that was missing.
- **Rule 7.** The Shape now argues the exemption: `rev-parse` with
  `<commit>:<path>` reads the object store, not the index, so neither hooks nor
  the fsmonitor run. I accept it, and it is now recorded rather than silent.

## 5. The radius grammar: resolved

Every edge form I listed is now defined. Messages name the entry and both
allowed forms, and segments that start with a dot are allowed.

I checked the grammar as written against every committed `plan.md` radius.
All entries pass, including `.claude/skills/factory/**`, `.claude/hooks/**`,
`.factory/<n>/**`, `.gitignore` and `.pre-commit-config.yaml`.

## 6. `ARTIFACTS`: resolved

The decision against the issue's "ARTIFACTS grows to match" is now recorded
under "Decisions I made", with its reason. `LOOP_ARTIFACTS` is named in
criterion 6 and includes `run.md`, and `present` covers both tuples.

## 7. `artifacts.md` scope: resolved

Criterion 11 now adds `run.md`, the radius grammar that replaces "list of
globs", and the list grammar.

## 8. Smaller gaps: resolved

- Criterion 1 decides quotes (kept verbatim) and covers a list next to a block.
- Criterion 4 is now about the diff plus the unmodified suite, which a test can
  decide.
- Criterion 5 decides that an absent or unreadable key gives an empty tuple.
- The Shape documents the split between `proof` and `has_proof`.

## Notes, not findings

- **Criterion 1's "ends where it should".** The phrase quoted above is the
  weakest wording left. The tests will define it, but the plan should name the
  rule: a block list's items are the indented `- ` lines up to the next line at
  column 0. A blank line or a `#` comment inside a list should neither end it
  nor make it unreadable, or the test should say otherwise. The
  differing-indentation rule in criterion 3 covers the nested-list case I
  raised.
- **`blob` without `git`.** Cycle 1's decision "`blob` raises nothing" is gone
  from the spec. When `git` is not on PATH, `subprocess` raises
  `FileNotFoundError`. Either keep the old rule (return `None`), or say that a
  missing `git` raises. The test's own `git commit` should also run with
  `user.name`/`user.email` set and an empty `core.hooksPath`, so a developer's
  global hooks cannot run inside it.
- **The Supersedes note.** When criterion 11 lands, `artifacts.md`'s
  Supersedes line for #139 should come out, as #214 did for its own notes.

## What this review could not verify

- I did not run pytest, and no implementation exists yet.
- I checked the radius grammar and the mapping rule with my own reading of the
  Shape, in a scratch script. The Builder's implementation could still differ
  from it.
