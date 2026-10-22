---
ticket: 139
stage: design
method: suite
criteria:
  - a top-level key followed by indented "- item" lines reads as a tuple of those items, in order, each stripped of surrounding whitespace
  - an inline empty list "key: []" reads as an empty tuple, and an inline "key: [a, b]" reads as ("a", "b")
  - a block list whose items are mappings ("- id: x") is not read at all, so the key is absent from the lists rather than half-read
  - front_matter's signature and its answers on every existing input are unchanged, and lists come through a separate function
  - Chain exposes spec_review, acceptance, proof, answers and park as parsed front matter, and criteria and radius as tuples
  - ARTIFACTS keeps its current six names, and the new files are tracked separately, so session_report's chain listing is unchanged
  - Chain.version is 2 exactly when intent.md carries "chain: 2", and 1 otherwise, including when intent.md is absent
  - blob(repo_root, commit, relpath) returns git's blob id for the file at that commit, or None when it does not exist there, and returns the same id for content checked out with CRLF and committed with LF
  - radius_errors(entries) accepts a relative POSIX file path or "dir/**" with no other glob characters, and names each entry it rejects
  - every chain committed under .factory/ parses without error, every plan.md radius in them passes radius_errors, every one reads as version 1, and routing.resolve answers each without raising
  - docs/factory/artifacts.md carries a contract for acceptance.md, proof.md, answers.md and park.md, and the chain field of intent.md, each naming the ticket that first writes it
specified_by: claude
specified_at: 2026-10-22
---

# Spec: chain v2

## Source

Issue #139 as rewritten on 2026-10-22, and `docs/factory/design.md` §5
(`chain.py`) and §6.

## Shape

- **`front_matter_lists(path) -> dict[str, tuple[str, ...]]`** sits beside `front_matter`, which is untouched.
  - Lists are read only at the top level.
  - An item containing `: ` is a mapping, and makes the whole key unreadable rather than half-read.
  - That follows the module's own principle: "a reader that quietly half-understands a nested structure is worse than one that does not try".
- **`Chain`** gains:
  - `spec_review`, `acceptance`, `proof`, `answers` and `park` as `dict[str, str]`;
  - `lists`, which is `front_matter_lists` per artifact name;
  - properties `criteria` (from `spec.md`), `radius` (from `plan.md`), and `version`.
- **`LOOP_ARTIFACTS`** holds the four new names. `present` covers both tuples. `ARTIFACTS` stays the six stage-order names, because `session_report` prints a line per name, and a v1 session should not be told it is missing a v2 file.
- **`blob`** shells out to `git rev-parse <commit>:<relpath>`, the content id git already computed after its own line-ending normalisation.
  - No hook calls it: hooks avoid subprocesses on every edit.
  - It does not touch the working tree.
- **`radius_errors`** returns a message per bad entry. Allowed forms:
  - a relative path with no `*`, `?` or `[`, and no `..` segment;
  - a directory followed by `/**`, under the same restrictions.

  Absolute paths are rejected. Overlap between two allowed entries is then a prefix comparison (re-check d). Today's matcher (merge.py's `full_match`) compares a path against a glob, never a glob against a glob.

## Verification method: suite

- **Red tests:**
  - list reading;
  - `version`;
  - `blob` with CRLF;
  - `radius_errors`;
  - the new `Chain` fields.

  Each is red today, because none of these exist.
- **The guard against regressions** is the existing suite, unmodified. Routing is not touched, so every existing chain keeps its stage by construction. Also a new test over every committed `.factory/*/` chain: it parses, its radius is valid, it reads as version 1, and `routing.resolve` answers it without raising.

## Decisions I made

- **Flow lists `[a, b]` are split on commas, with no quote handling.** No real artifact writes a quoted flow list. `docs_cleared: []` is the only flow list in the tree.
- **`version` reads `intent.md`, not `spec.md`.** `feature new` (#222) writes `intent.md` first, so a chain is v2 from birth.
- **`blob` raises nothing.** A missing commit or path gives `None`, matching the module's rule that a missing artifact is absent, never an error.

## Not in scope

Any routing change (#218), the commands that write the new artifacts, and the
factory loop.
