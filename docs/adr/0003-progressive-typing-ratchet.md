---
status: accepted
---

# Progressive Pyright ratchet: a floor for the whole repo, `strict` grown one directory at a time

## Context

The repo had no type-checking gate at all. A `pyright` run against the full
tree at `strict` reports 9202 errors across 193 files; not one directory is
already clean at that mode. A single big-bang migration to `strict` is not a
realistic landing — it would either block on fixing thousands of pre-existing
errors before the gate could ship, or ship the gate and immediately fail on
every commit that touches an untyped file, which is the same thing as no
gate at all.

The alternative extreme — no typing gate, ever — was considered and rejected:
`reportArgumentType`, `reportOptionalMemberAccess`, and
`reportAttributeAccessIssue` are the top offenders even at the cheap
`standard` mode, and this is exactly the class of bug a runtime-only bot
discovers by crashing mid-session rather than at commit time.

## Decision

**A floor, plus one directory held to a tighter bar, grown over time.**

- The whole governed tree must pass Pyright `standard` — cheap (`basic` →
  `standard` costs under 20 errors repo-wide) and catches real bugs
  (`reportArgumentType`, `reportOptionalMemberAccess`, `reportCallIssue`)
  that `basic` misses.
- One directory — `botting/controller/inputs/`, chosen for being stub-clean
  and load-bearing (ADR 0002's input send path) — is held to `strict`, in an
  **append-only** list (`[tool.pyright].strict` in `pyproject.toml`). Growing
  the list admits a directory once it clears the stub-cleanliness gate; it
  never removes one, and no override may loosen a listed directory below
  what `strict` already catches.
- Admission does **not** require the directory to already be clean.
  `botting/controller/inputs/` entered carrying 184 strict errors across all
  6 of its files — accepted debt, not a blocker. Debt inside and outside the
  Strict List is paid down the same way: fixed as each file is next touched
  (the boy-scout rule), never bulk-fixed as part of landing or growing the
  gate.
- Every hook (`ruff`, `pyright`) runs **staged-files-only** — `pass_filenames`
  at its default, no `always_run`. This is what makes "touching one file
  surfaces every violation in that file" true without also meaning "touching
  one file surfaces every violation in the repo."

See [`docs/agents/typing.md`](../agents/typing.md) for the full ratchet
mechanics, the "strongly typed" definition, and the measured baseline.

## Consequences

- **The Strict List can only ever grow slower than the codebase's real
  typing coverage** — a directory can be strongly typed in practice for a
  long time before someone proposes adding it. That lag is accepted; the
  list is a floor-raising mechanism, not a certification.
- **Cadence and per-directory-vs-per-file granularity for growing the list
  past its first entry are not decided by this ADR** — see the quality-gates
  map's *Not yet specified* section (issue #76).
- Rejected: **big-bang migration to `strict`** (blocks landing any gate on
  fixing ~9000 pre-existing errors first) and **no gate at all** (the bugs
  `standard` catches are exactly the ones this bot currently discovers at
  runtime).
- **Bulk-fixing pre-existing debt — repo-wide or inside the Strict List — is
  explicitly out of scope for this decision.** A dedicated bulk-fix effort,
  if ever wanted, is argued and scoped on its own; this ratchet does not
  presuppose it will happen.
- Delivered by issue #76 (the quality-gates map): #79 decided the Ruff rule
  set, #80 decided the `standard` floor and the pilot Strict List entry, #81
  landed the config and hooks, #82 (this ADR) wrote it down.
