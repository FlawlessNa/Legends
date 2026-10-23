---
ticket: 139
stage: design
method: suite
criteria:
  - a top-level key followed by indented "- item" lines reads as a tuple of those items in order, each stripped of surrounding whitespace with quotes kept verbatim, and a list followed by a nested block or another key ends where it should
  - an inline empty list "key: []" reads as an empty tuple, and an inline "key: [a, b]" reads as ("a", "b")
  - an item is a mapping only when the text after "- " starts with a word followed by a colon and then whitespace or the end, as in "- id: x", and a key holding any mapping item, or items at differing indentation, is absent from the lists rather than half-read, while prose items containing ": " are read
  - the diff does not change front_matter's body or signature, the existing suite passes unmodified, and lists come through a separate function front_matter_lists
  - Chain exposes spec_review, acceptance, proof, answers and park as parsed front matter, and criteria and radius as tuples that are empty when the key is absent or unreadable
  - ARTIFACTS keeps its current six names and LOOP_ARTIFACTS holds acceptance.md, proof.md, answers.md, park.md and run.md, and present covers both, so session_report's chain listing is unchanged
  - Chain.version is 1 when intent.md is absent or has no chain key, 1 for "chain: 1", 2 for "chain: 2", and raises UnknownChainVersion for any other value
  - blob(repo_root, commit, relpath) takes a POSIX path relative to the repo root, returns the blob id of that file at that commit, returns None for a missing commit, a missing path or a directory, and in a repo with core.autocrlf=true and the file on disk with CRLF it returns the id of the LF content
  - radius_errors(entries) accepts a relative POSIX file path, or a directory followed by "/**", with no "*", "?", "[" or backslash elsewhere, no empty, "." or ".." segment, no leading "/" or drive letter, and no trailing "/", and each message names the entry and the two allowed forms
  - for every chain committed at 9654223 (tickets 140, 153, 162, 179, 189, 191, 194, 197, 199, 202, 206, 209 and 214), each spec.md that writes criteria reads a non-empty tuple whose length equals its "- " lines under that key, each plan.md radius is non-empty and passes radius_errors, each reads as version 1, and routing.resolve answers each without raising, blocked answers included
  - docs/factory/artifacts.md carries contracts for acceptance.md, proof.md, answers.md, park.md and run.md and for intent.md's chain field, each naming the ticket that first writes it, replaces plan.md's "list of globs" with the radius grammar, and states the list grammar
specified_by: claude
specified_at: 2026-10-22
revised_after: spec-review.md (changes-requested, 8 findings)
---

# Spec: chain v2

## Source

Issue #139 as rewritten on 2026-10-22, and `docs/factory/design.md` §5
(`chain.py`) and §6.

## Shape

- **`front_matter_lists(path) -> dict[str, tuple[str, ...]]`** sits beside `front_matter`, which is not touched.
  - It reads lists at the top level only: block lists (`key:` followed by indented `- item` lines) and flow lists (`key: []`, `key: [a, b]`).
  - **A mapping item** is one whose text after `- ` matches `^[A-Za-z_][A-Za-z0-9_]*:(\s|$)`, the module's own key pattern. Any mapping item, or items at differing indentation, makes the whole key absent, never half-read. That follows the module's own rule: "a reader that quietly half-understands a nested structure is worse than one that does not try".
  - **Prose items stay readable.** Real criteria often contain `: ` mid-sentence (`.factory/197/spec.md:11`, and this spec), so prose that merely contains a colon is not a mapping.
- **`Chain`** gains:
  - `spec_review`, `acceptance`, `proof`, `answers` and `park`, each a `dict[str, str]`;
  - `lists`, which is `front_matter_lists` for each artifact name;
  - `criteria` and `radius`, each a tuple that is empty when the key is absent or unreadable;
  - `version`.

  `proof` is `proof.md`'s front matter. The v1 `has_proof`, which reads `plan.md`'s `proof.suite`, keeps its meaning, and both docstrings say so.
- **`LOOP_ARTIFACTS`** is `acceptance.md`, `proof.md`, `answers.md`, `park.md` and `run.md`. `present` covers it and `ARTIFACTS`.
- **`version`** maps `chain` absent to 1, `"1"` to 1, and `"2"` to 2. Anything else raises `UnknownChainVersion`, the same rule as `MalformedVerdict`: guessing silently decides the ticket. `front_matter` does not strip comments, so `chain: 2  # x` raises. That is the right answer for a field no person should be hand-editing.
- **`blob`** runs `git -C <repo_root> rev-parse --verify --quiet <commit>:<relpath>^{blob}` and returns the id on exit 0, else `None`.
  - `^{blob}` makes a directory answer `None` rather than a tree id.
  - `--quiet` keeps a failure off stdout.
  - Design §4 rule 7's `-c` flags are for git commands that run hooks or the fsmonitor, and `rev-parse` runs neither.
  - No hook calls it.
- **`radius_errors(entries) -> tuple[str, ...]`** returns one message per bad entry, each naming the entry and the two allowed forms: `path/to/file` or `path/to/dir/**`.
  - Rejected: absolute paths (a leading `/` or a drive letter), backslashes, a bare `**`, `**` anywhere but a final `/**`, any other `*`, `?` or `[`, empty, `.` or `..` segments, and a trailing `/`.
  - A segment that merely starts with a dot (`.claude`, `.factory`) is fine.

## Verification method: suite

- **Red tests** cover:
  - block and flow lists;
  - mapping detection, including the prose case;
  - a list next to a nested block;
  - `version`, including the raise;
  - `blob`, in a temporary repo with `core.autocrlf=true`, asserting the file on disk has CRLF and the answer equals `git hash-object` of the LF content, plus the `None` cases;
  - `radius_errors`, over every edge form above;
  - the new `Chain` fields.

  Each is red today because none of these exist.
- **The real-chain test** pins the thirteen tickets committed at `9654223` by number, so a future `chain: 2` ticket cannot break it. It checks:
  - criteria counts against the raw `- ` lines;
  - non-empty valid radii;
  - version 1;
  - that `routing.resolve` answers each without raising. Tickets 153, 179 and 191 come back blocked today, which is allowed.

## Decisions I made

- **`ARTIFACTS` does not grow, despite the issue's "ARTIFACTS grows to match".** `session_report` prints one line per `ARTIFACTS` name (`hooks.py` `_chain_lines`). Growing it would tell every v1 session it is missing five v2 files. Routing checks explicit names, so a separate tuple loses nothing.
- **Flow lists split on commas, with no quote handling.** The only flow list in the tree is `docs_cleared: []`.
- **`version` reads `intent.md`**, because `feature new` (#222) writes it first, so a chain is v2 from birth.

## Not in scope

Any routing change (#218), the commands that write the new artifacts, and the
factory loop.
