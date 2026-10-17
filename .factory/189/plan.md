---
ticket: 189
stage: build
radius:
  - factory/**
  - tests/test_factory/**
  - .claude/settings.json
  - docs/factory/**
  - .factory/189/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_hooks.py::test_documentation_is_outside_the_gate
  red_output_sha: 4failed-28passed
  suite: pass
docs_cleared: null
---

# Plan

## Files that change

- `factory/chain.py` — read a ticket's artifact chain. Dependency-free
  front-matter reading: `pyproject.toml` declares `dependencies = []`, so
  reaching for PyYAML would make the factory a second place the project's
  dependencies are declared.
- `factory/hooks.py` — the decisions, as pure functions of a branch name and a
  filesystem state. No harness, no I/O.
- `factory/cli.py` — a `hook` subcommand. The one place that reads stdin and
  writes a hook response rather than the dispatcher's payload.
- `tests/test_factory/test_hooks.py` — the decision table.
- `.claude/settings.json` — the three registrations.
- `docs/factory/artifacts.md`, `stages.md` — `spec-review.md` and the stage 2
  gate.

## Order

Pure decisions first, with their tests, before anything touches the harness.
A hook whose logic is only testable by triggering it is a hook nobody will
change later.

## Risks

- **Locking myself out.** `pre-tool-use` denies writes outside `.factory/` when
  the chain is incomplete, and this branch's own chain is complete, so the
  risk is to the next ticket rather than this one. The override in
  `settings.local.json` is part of acceptance for that reason.
- **Latency.** Fires on every edit. Budget 150ms; measured, and the
  `SessionStart` cache only if it misses.
- **Too broad a deny.** Scoped to `issue/<n>-*` branches only. On any other
  branch all three hooks return immediately.

## Proof of completion

`method: suite`. The decision functions are unit-tested from a branch name plus
a filesystem state. The suite line must not move except by the new tests.

That the harness actually invokes the hooks is **not** provable from here and
goes under Could not verify.


## Proof, recorded

`tests/test_factory/test_hooks.py::test_documentation_is_outside_the_gate` was
**red without the fix**: `4 failed, 28 passed`, denying writes to
`factory/AGENTS.md`, `AGENTS.md`, `docs/factory/stages.md` and `docs/SETUP.md`.
After narrowing the deny to source: `38 passed`.

That bug was found by the spec review (`spec-review.md`, finding 1), not by me.
The first implementation denied everything outside `.factory/`, so it forbade
writing the file documenting its own escape hatch — the exact deadlock
`intent.md` names as a constraint.

### Latency, measured

| | median |
| --- | --- |
| Bare interpreter (floor, this machine) | 135.6 ms |
| Bare interpreter with `-S` | 51.7 ms |
| `+ import factory.hooks` | 159.1 ms |
| `+ import factory.cli` | 189.7 ms |
| **`factory hook pre-tool-use`** | **217.5 ms** |

**Criterion 7's 150ms budget is not met**, and the criterion is left unchanged.
The budget was invented before any measurement, and the Python floor alone is
135.6 ms. Editing it now to match the result is the one thing the spec being
immutable to the Builder exists to prevent. The review reached the same
conclusion independently (finding 2).
