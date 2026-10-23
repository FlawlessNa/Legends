---
ticket: 139
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: a chain reader the agreed design can stand on

## Problem statement

The factory loop, routing v2 and the new commands all read the chain. Today's
reader cannot give them what they need:

- **It cannot read lists.** `front_matter` skips every line starting with `-`
  (chain.py:122). So `criteria` in `spec.md` and `radius` in `plan.md` are
  invisible, although every real chain writes them as lists.
- **It does not know the artifacts the design adds:** `acceptance.md`,
  `proof.md`, `answers.md` and `park.md`. `spec-review.md` is detected but never
  parsed.
- **It has no stable way to say "this is the same content".** The design binds
  acceptance and proof to content. `core.autocrlf=true` rewrites line endings on
  checkout, so hashing the working file gives different answers for the same
  spec (review finding M7).
- **It cannot tell a v2 chain from a v1 chain.** Routing v2 (#218) must leave
  every existing chain on today's rows.

## Proposed outcome

The chain reader reads block lists, knows every artifact in
`docs/factory/design.md` §6, offers git's own content id for a file at a
commit, recognises a v2 chain by a positive marker, and refuses a radius entry
it could not compare with another. Contracts for the new artifacts are written
in `artifacts.md`.

## Affected users and systems

- `factory/chain.py` and its tests.
- `docs/factory/artifacts.md`.

The hooks import `chain.py` on every edit, so it must stay cheap and
dependency-free.

## Constraints

- No behaviour of any existing caller changes. Routing, the hooks and `factory
  next` keep their answers on every existing chain.
- No YAML dependency (`pyproject.toml` declares `dependencies = []`).

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap ("proceed, let's
continue progress", 2026-10-22), and this ticket's body was rewritten from the
agreed design.
