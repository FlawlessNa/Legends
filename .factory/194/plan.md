---
ticket: 194
stage: build
radius:
  - factory/merge.py
  - factory/cli.py
  - factory/AGENTS.md
  - tests/test_factory/test_merge.py
  - .github/workflows/merge-policy.yml
  - docs/factory/**
  - .factory/194/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_merge.py::test_a_diff_touching_botting_is_refused
  red_output_sha: null
  suite: pass
docs_cleared: null
---

# Plan

## Files that change

- `factory/merge.py` — new. The policy's values (`Policy`, `POLICY`), the facts
  (`PullRequestFacts`, `TicketFacts`, `CheckRun`), the pure `evaluate`, the
  `verdict` that maps failures to an exit code, the gatherer that reads GitHub
  through an injected `gh` runner, and `check(pr)` returning
  `(ExitCode, payload)` the way every handler does.
- `factory/cli.py` — one `COMMANDS` entry, `merge`, with a nested `check`
  action. Nested rather than two positionals so that `factory merge` alone still
  parses, which `test_every_registered_command_is_reachable_through_the_parser`
  requires — that test stays untouched.
- `factory/AGENTS.md` — the command, and why the protected set is the import
  closure.
- `tests/test_factory/test_merge.py` — new. Per-condition tests from constructed
  facts; the gatherer against recorded `gh` output; the import closure; the
  doc; the workflow YAML (PyYAML is already pinned in `requirements.txt`).
- `.github/workflows/merge-policy.yml` — new. The repo's first workflow.
- `docs/factory/merge-policy.md` — new. The policy, stated once.
- `docs/factory/README.md` — links it. `bootstrap.md` gains its row in "What is
  actually enforced today"; `stages.md` stage 9 points at it.

## Order

1. `merge.py` evaluation and its tests, from constructed facts. No I/O.
2. The gatherer and its tests, against recorded output.
3. The CLI entry.
4. The workflow, then its test.
5. The docs, then their test.

## Hard-stop check

The radius intersects no `AGENTS.md` hard-stop path: no input, focus, ledger,
telemetry envelope or transport, map JSON, pinned dependency, parked module, or
anything an ADR decides. `.github/workflows/` is new and on no list.
`pyproject.toml` is **not** touched — the console script already exists.

## Risks

- **The workflow cannot be exercised from here.** GitHub runs it from `dev`'s
  copy only. Every property that can be read from the YAML is tested by parsing
  it; the rest goes under Could not verify.
- **`gh` output shapes.** Recorded from this repo (#196) on 2026-10-17 with
  `gh` 2.98.0: compact JSON per line under `--jq`, `previous_filename` null
  for non-renames.
- **The protected set narrows `factory/**` sharply**, because almost every
  factory ticket touches `cli.py`. Recorded as reversible in the PR.

## Proof of completion

`method: suite`. The tests named in the spec criteria, plus the full suite
shape. Red without the change: stash `factory/merge.py` and `factory/cli.py`
(structural: the module does not exist), **and** a behavioural red — neutralise
the path-allowlist and method checks in turn and show
`test_a_diff_touching_botting_is_refused` and
`test_a_method_live_ticket_is_refused` fail on their assertions.


## Proof, recorded

**Suite**, from the repo root, no flags:
`1051 passed, 3 skipped, 25 deselected` — 0 failed, 0 errors, 0 xfailed.
`tests/test_factory/test_merge.py` is 84 of those. `ruff check`,
`ruff format --check` and `pyright` clean on `factory/merge.py`,
`factory/cli.py`, `tests/test_factory/test_merge.py`.

**Red without the change, structural.** `git stash push -u -- factory/merge.py
factory/cli.py`, test kept:

```
E   ModuleNotFoundError: No module named 'factory.merge'
1 error in 1.37s
```

**Red without the change, behavioural** — the stronger proof, since the
structural one would hold for any new module. Each check disabled in turn,
everything else intact:

```
allowlist check removed -> test_a_diff_touching_botting_is_refused
E   AssertionError: assert set() == {<Condition.PATHS_ALLOWED: 'paths-allowed'>}

method check removed -> test_a_method_live_ticket_is_refused
E   AssertionError: assert set() == {<Condition.TICKET_METHOD: 'ticket-method'>}
```

`set()` is the point: without the check, a `botting/` diff and a `method:live`
ticket each evaluate to *no failures* — they would merge. Source restored
byte-identical (`cmp`), 84 passed.

**Against real GitHub, read-only**: `factory --json merge check 196` reads
#196 correctly and refuses it with exit 3 on `ticket-type` (`type:build`),
`paths-allowed` (`.factory/189/*`), `not-self-change` (`factory/cli.py` and
friends) and `checks-green` (none reported). Every one of those is right.

`red_output_sha` stays `null`: #145 has not defined what it hashes.
