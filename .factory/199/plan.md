---
ticket: 199
stage: build
radius:
  - .claude/settings.json
  - .claude/hooks/**
  - .claude/skills/factory/**
  - factory/**
  - tests/test_factory/**
  - docs/factory/**
  - .pre-commit-config.yaml
  - scripts/**
  - .factory/199/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_hook_wiring.py::test_the_command_does_not_depend_on_an_activated_venv
  red_output_sha: 4failed-2passed
  suite: pass
docs_cleared: null
---

# Plan

## Files that change

- `.claude/hooks/factory-hook.sh` — new. Resolves an interpreter and says so
  loudly when it cannot.
- `.claude/settings.json` — the three hooks call the launcher.
- `factory/chain.py` — `_git_dir`, so `HEAD` is found in a linked worktree.
- `factory/hooks.py` — the `factory gates: LIVE` heartbeat.
- `.claude/skills/factory/SKILL.md` — step 0: notice a missing heartbeat.
- `tests/test_factory/test_hook_wiring.py` — new, runs the configured string.
- `tests/test_factory/test_hooks.py` — worktree regression tests.

## Two bugs, not one

The ticket reported the PATH failure. Writing the test for it immediately
surfaced a second, worse one: in a linked worktree `.git` is a *file*, so
`current_branch` found nothing and every gate concluded "not a ticket branch".
`factory claim` gives each ticket a worktree, so the gates were dead in exactly
the environment they exist for.

## Proof

**Red without the change.** The wiring tests, run against the pre-fix
configuration, gave `4 failed, 2 passed` — three events unreachable plus the
round-trip. After: `47 passed` in `tests/test_factory`, `976 passed` for the
whole suite, pyright clean.

`test_the_command_does_not_depend_on_an_activated_venv` is the negative control
the review asked for: it fails against the old `factory hook <event>` string,
so a green suite is evidence rather than decoration.

## Decisions I made

- **Detection in, fail-closed out.** The review showed those are separable and
  that the spec wrongly deferred both. Detection is a heartbeat; enforcement is
  untouched.
- **A positive heartbeat rather than a louder error.** A hook that cannot run
  emits nothing, so no error-based signal can work. Absence of
  `factory gates: LIVE` is the alarm.
- **Launcher script rather than a longer command string.** It needs branching to
  find the main repo's venv from a worktree, which a settings string cannot
  express, and it gives #149/#150/#194 one place to inherit.


## Radius extended mid-ticket, deliberately

Added `.pre-commit-config.yaml` and `scripts/`. Committing surfaced a **third**
instance of the same root cause: pre-commit hardcodes `./.venv/Scripts/ruff.exe`
and `pyright.exe`, which do not exist in a linked worktree, so ruff and pyright
reported `Executable not found` and the commit was refused.

Three bugs, one assumption: **tooling assuming `.venv` sits beside the code.**
The hooks, the chain reader, and now pre-commit. Fixing two and leaving the
third would have meant every worktree commit either fails or skips its linters.

`scripts/venv-tool.sh` resolves the same way the hook launcher does, with one
deliberate difference: **it exits non-zero when no venv is found.** A hook that
cannot run should fail open and say so; a commit that silently skips ruff and
pyright should stop.
