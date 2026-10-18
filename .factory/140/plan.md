---
ticket: 140
stage: build
radius:
  - factory/**
  - tests/test_factory/**
  - .claude/skills/factory/**
  - docs/factory/**
  - .factory/140/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_routing.py::test_every_method_can_reach_integrate
  red_output_sha: see-below
  suite: pass
docs_cleared: []
---

# Plan

## Files that change

- `factory/routing.py` — new. The table as a function.
- `factory/chain.py` — `intent`, `review`, `qa` front-matter; `accepted`,
  `has_review`, `has_qa`, `needs_qa`.
- `factory/cli.py` — the `next` subcommand.
- `tests/test_factory/test_routing.py` — new, 24 tests.
- `.claude/skills/factory/SKILL.md` — the stub **deleted**.
- `docs/factory/artifacts.md` — the verdict domain.

## The review changed the design three times

The spec called the stub's ten rows "the specification". Review walked them
against real chains and found the table itself unsound. All three are fixed
here, and none was my idea:

1. **No fixed point.** A `method: live` ticket could match the build row on
   every call, leaving review, QA, document and integrate unreachable.
   `test_every_method_can_reach_integrate` now proves a terminal row exists for
   every legal method.
2. **A rejected review was an absorbing state.** Nothing routed it back to the
   Builder, so every rejection needed a human to edit an artifact by hand.
   `changes-requested` now routes to Build; only `fail` stops.
3. **A late amendment was destructive.** A ticket at QA with `spec-review.md`
   missing routed to Design, where the Specifier rewrites the spec that the
   plan, the implementation and a passing review were contracted against. A
   hole upstream with work downstream now **blocks** instead: redoing is more
   destructive than stopping.

Plus the verdict domain, which my first implementation got wrong in exactly the
way review predicted — an unfinished review read as a rejected one.

## Proof

`test_every_method_can_reach_integrate` is red without the method-aware
termination: with the original table a `live` ticket never leaves
`build-implementing`. The suite moves from 1069 to 1093 passing.

## Decisions I made

- **`fail` versus `changes-requested`.** The stub had one failure state; it
  needed two, because "fix it" and "a person must decide" are different
  answers. Recorded rather than asked, per Decide and record.
- **A hole upstream blocks rather than rerouting.** The review suggested gating
  the early rows on no downstream artifact existing. Blocking is stricter and
  names the inconsistency, which seemed better than silently choosing which
  artifact to trust.
