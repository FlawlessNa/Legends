---
ticket: 162
stage: build
radius:
  - factory/models.py
  - factory/cli.py
  - factory/merge.py
  - configs/factory-models.toml
  - tests/test_factory/test_models.py
  - tests/test_factory/test_cli.py
  - docs/factory/artifacts.md
  - docs/factory/merge-policy.md
  - .factory/162/**
tasks: null
merge_order: null
proof:
  red_test: null
  red_output_sha: null
  suite: null
docs_cleared: null
---

# Plan: the model routing table

## Radius

Nine paths, and the reason each is in it:

| Path | Why |
| --- | --- |
| `factory/models.py` | the resolver - new |
| `factory/cli.py` | registers `factory model` in `COMMANDS` |
| `factory/merge.py` | `models.py` joins `protected_paths`, or `test_merge.py` goes red |
| `configs/factory-models.toml` | the table - new |
| `tests/test_factory/test_models.py` | the tests - new |
| `tests/test_factory/test_cli.py` | the command's registration and exit codes |
| `docs/factory/artifacts.md` | reserves the `model` field name |
| `docs/factory/merge-policy.md` | the protected list is duplicated there by design |

**Not in the radius, deliberately:**

- `pyproject.toml` - a hard-stop path. The table lives in `configs/` precisely
  so this ticket never needs to touch it (`spec.md` -> The table's home).
- `factory/routing.py` and `factory/chain.py` - `Stage` and `front_matter` are
  imported, not changed. If either needs changing, that is a different ticket
  and this plan is wrong.
- `.claude/**` - nothing here is a hook or a permission.

## Order of work

1. `configs/factory-models.toml` first, since it is the specification made
   concrete and everything else is written against it.
2. `factory/models.py`: load, validate, resolve. Validation before resolution,
   because a table error must be reported as a table error even when the stage
   asked about happens to resolve cleanly.
3. `tests/test_factory/test_models.py`.
4. `factory model` in `cli.py`, then `test_cli.py` for the exit codes.
5. `merge.py` and `merge-policy.md` - and run `test_merge.py` to confirm the
   closure test is satisfied rather than assuming it.
6. `artifacts.md`.

## The shape

    @dataclass(frozen=True)
    class Choice:
        model: str | None
        tier: str | None
        rule: str          # which rule fired, in words
        record: str        # the contracted line

    class TableError(Exception): ...        # -> exit 3

    def load(path: Path) -> Table           # validates everything, or raises
    def resolve(table: Table, stage: Stage, chain: Chain | None) -> Choice

`load` validates the **whole** table, not the part a given call touches. A
transposed name in `unavailable` must be an error on the first call, not on the
one that happens to need that tier.

`chain` is optional because `--stage` can be asked with no ticket. A `None`
chain means every fact is "not yet knowable", so no override fires - which is
the correct answer, not a degraded one.

## Proof

The criteria this plan expects to be red without the change, with the one
chosen as `proof.red_test` named at stage 5:

- an unavailable first entry in a chain is skipped
- an override beats the stage table, and the first of two matching wins
- an override routing *down* is a table error
- a transposed name in `unavailable` is a table error
- a stage absent from the table resolves to `standard`, at exit 0
- `integrate` answers `model: null`, at exit 0
- argument errors are 2 and table errors are 3

## What I expect not to be able to verify

- **That any alias is real.** No test can establish that `opus` names a model a
  harness will accept. The suite proves the table's logic, not its contents.
- **That the Foreman uses it.** Nothing consumes `factory model` until #159.
- Nothing here touches the bot: no input path, no timing, no keystroke.
