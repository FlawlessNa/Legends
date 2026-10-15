---
ticket: 191
stage: plan
accepted_by: nassim
accepted_at: 2026-10-15
---

# Intent: retire the CLAUDE.md shims

## Problem statement

Four `CLAUDE.md` files exist solely to import the `AGENTS.md` beside them. They
were a workaround for Claude Code not reading `AGENTS.md`, and that limitation
is gone: native support landed in v2.1.277, and the installed client is 2.1.299.

Nassim: *"CLAUDE.md should move away entirely; newer versions of Claude now
support AGENTS.md, so let's use the latter."*

## Proposed outcome

No `CLAUDE.md` anywhere in the tree. `AGENTS.md` at the root and beside each
package is read directly, at the root on session start and per-directory when a
file there is opened.

## Affected users and systems

- Every Claude Code session in this repo.
- Anyone on a client older than v2.1.277, who will load **nothing** from these
  files after this change, silently.
- #137's branch, which adds `factory/CLAUDE.md` and would reintroduce the
  problem if merged after this.
- #163, since subagents that start without project instructions do not get
  these files either.

## Constraints

- **All-or-nothing.** A `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md`
  anywhere in the working directory or above makes Claude read the `CLAUDE.md`
  files *only* and ignore `AGENTS.md` entirely. A partial migration leaves the
  repo worse than it started.
- The same rule applies per directory, so every package shim goes together or
  that package's rules stop loading without saying so.

## Open questions

- Where does genuinely Claude-specific guidance live now? `.claude/AGENTS.md`
  is also read. Nothing currently needs it: the root `CLAUDE.md`'s only content
  describes the shim arrangement being deleted.
