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
  red_test: tests/test_factory/test_hooks.py::test_a_ticket_branch_in_the_primary_checkout_is_still_refused
  red_output_sha: see .factory/209/plan.md -> Proof
  suite: pass
docs_cleared: []
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

**`pytest`: 1197 passed, 3 skipped, 25 deselected.** 0 failed, 0 errors, 0
xfailed. ruff, ruff format and pyright clean. `tests/test_factory/` 241 -> 268.

Three red-proofs, one per load-bearing piece:

| Reverted | Red |
| --- | --- |
| row 1 removed entirely | **12** |
| the identity check dropped | **4**, including "another repository is never refused" |
| `_is_primary` by path name rather than by kind | **1**, the `worktrees`-named repository |

The third is a one-test proof on purpose: it is the exact misclassification the
first draft shipped, and nothing else notices it.

### Two defects my own tests caught, not review

1. **`_exempt_in_primary` ignored the universal exemptions**, so `.factory/`,
   `docs/` and `AGENTS.md` were refused in the primary checkout. That is #189's
   deadlock precisely - the gate forbidding the artifact that satisfies it -
   and `test_the_artifacts_stay_writable_in_the_primary` went red on the first
   run. Review had warned about this shape for a *different* constant; it bit
   on a third one.

2. **The `repo` fixture was not a worktree.** It held its own `.git`
   *directory*, which is structurally a primary checkout, so every test using
   it exercised a shape this repo never produces - and two report tests failed
   because the new line correctly fired on it. Rebuilt as a genuine linked
   worktree of `off_ticket`, with a real `gitdir:` pointer, so the pair is one
   repository as they always claimed.

   The same was true of the cross-worktree tests #206 added: they paired two
   sibling directories, each its own repository, so
   `test_a_ticket_session_writing_to_the_trunk_is_still_judged` never modelled
   a Builder writing the trunk. **Two tickets' tests were passing on fixtures
   that could not occur.**

### What actually changed, against what the spec predicted

`spec.md` predicted three of four tests would stay green and one would invert.
Wrong: **three changed.** Both cross-worktree tests had to be rebuilt on real
fixtures (the prediction assumed the sibling fixtures were one repository, and
they were not), and `test_neither_side_a_ticket_is_indifferent` inverted as
predicted. The suite was the arbiter, as the spec said it would be.

Red without the change, also verified:

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
