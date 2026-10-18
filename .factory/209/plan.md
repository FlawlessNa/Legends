---
ticket: 209
stage: build
radius:
  - factory/hooks.py
  - factory/cli.py
  - tests/test_factory/test_hooks.py
  - tests/test_factory/test_cli.py
  - AGENTS.md
  - docs/factory/stages.md
  - docs/factory/README.md
  - .claude/skills/factory/SKILL.md
  - .factory/209/**
tasks: null
merge_order: null
proof:
  red_test: null
  red_output_sha: null
  suite: null
docs_cleared: null
---

# Plan: refuse source writes in the primary checkout

## Radius

| Path | Why |
| --- | --- |
| `factory/hooks.py` | `_is_primary`, `_common`, the exemption constants, row 1, `OFF_TICKET`, `session_report` |
| `factory/cli.py` | the report's root resolves through `governing()` rather than raw `cwd` |
| `tests/test_factory/test_hooks.py` | the new cases, the linked-worktree fixture, one test that changes meaning |
| `tests/test_factory/test_cli.py` | the report's root, and the hook's end-to-end answer |
| `AGENTS.md` | the canonical, tool-neutral statement of the rule |
| `docs/factory/stages.md` | beside the other `[mechanical]` markers |
| `docs/factory/README.md` | the enforcement marker table |
| `.claude/skills/factory/SKILL.md` | an orchestrator asked to pick up a ticket reads this first |

**Not in the radius:**

- `factory/chain.py` — `git_dir` is already exported (#206 did that) and
  `_common` is built on it here rather than moved into it. If `chain.py` needs
  changing, this plan is wrong.
- `factory/merge.py` — no module joins the console script's import closure, so
  the protected list is unchanged. `test_merge.py` is still run to confirm it
  rather than assuming.
- `.claude/settings.json` — the matcher is #207's. Changing it here would also
  put a privilege-escalation path in a PR about scoping (#202).
- `configs/`, `botting/`, `maple/` — nothing here reaches them.

## Order of work

1. `_common` and `_is_primary`, with their tests, including the four-root table
   from `spec.md` and a **genuine linked-worktree fixture** (a real `gitdir:`
   pointer, since no existing fixture is one). Everything rests on these.
2. The exemption constants and their matcher, as a **separate** constant from
   `_ALWAYS_WRITABLE_ROOTS` — with the test that the new exemptions do *not*
   apply inside a ticket worktree written **before** the matcher, since that is
   the regression the review warned the obvious shortcut causes.
3. Row 1 in `decide_write`, ahead of everything.
4. Row 3's narrowing to targets inside this repository, and the #206
   over-reach test, which is red today.
5. Run the full suite and record **what actually changed**, against the four
   tests `spec.md` predicts. The table there is reasoning about code that did
   not exist; this step replaces it with fact.
6. The monkeypatch control test, which is also the revert rehearsal.
7. `OFF_TICKET`, both `session_report` paths, and the report's root.
8. `AGENTS.md`, `stages.md`, `README.md`'s marker table, `SKILL.md`.

## The shape

    PRIMARY_EXEMPT:       tuple[tuple[str, ...], ...]
    PRIMARY_REFUSED:      tuple[tuple[str, ...], ...]
    PRIMARY_EXEMPT_FILES: tuple[str, ...]

    def _common(root: Path) -> Path | None
    def _is_primary(root: Path) -> bool
    def _primary_refusal(target, session) -> Decision | None   # the one call site

`_primary_refusal` returning `None` means "this row does not apply", so
`decide_write` gains one `if` and nothing else. That is what makes the revert
one edit, and what the monkeypatch test proves is single-source.

## Proof

Red without the change, expected:

- the four-root identity table (another repo refused, a `worktrees`-named repo
  misread) — only testable once `_common` exists, so this is the forward proof
- a source write in the primary on a **ticket branch** with a complete chain
- the #206 scratchpad over-reach, **red against merged code today**
- `.claude/settings.local.json` refused in the primary
- the new exemptions leaking into ticket worktrees

## What I expect not to be able to verify

- **That the gate fires in a live session.** `-m factory` loads code from the
  process cwd, so this is inert in its own worktree until merged. Suite-only
  evidence, and it matters more here than in #206 because the subject of the
  gate is the primary checkout itself.
- **Whether `SessionStart`'s cwd is ever a subdirectory** of the primary. The
  fix for it is defensive; the condition is unobserved.
- **Git's `worktree.useRelativePaths`** (>= 2.48), which can change the
  `gitdir:` pointer shape. `_common` reads the resolved dir, so it should be
  unaffected; not verified against that config.
- Nothing here touches the bot.
