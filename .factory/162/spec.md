---
ticket: 162
stage: design
method: suite
criteria:
  - the table lives at configs/factory-models.toml and is read with stdlib tomllib, adding no runtime dependency
  - a stage routes to a tier, and a tier to the first model in its chain not declared unavailable
  - a stage in the vocabulary but absent from the table resolves to standard, at exit 0, with a reason naming the default
  - an override beats the stage table, a multi-key when is AND, and when several match the first in file order wins
  - an override may only name a tier strictly above the stage's, and a table that routes down is a table error
  - a fact name outside the closed vocabulary is a table error, while a known fact not yet knowable at this stage simply does not fire
  - argument errors exit 2 and table errors exit 3, and no error path ever resolves to a model
  - integrate answers model null at exit 0, a blocked chain exits 3 carrying blocked_by, and no ticket with no --stage is exit 2
  - every name in unavailable appears in some tier chain, no tier is empty, and every table key is a member of routing.Stage
  - the resolution carries the rule that fired and a record line of contracted shape
  - factory/models.py is in POLICY.protected_paths and in merge-policy.md, so the import-closure test stays green
specified_by: claude
specified_at: 2026-10-18
reviewed_by: see spec-review.md
---

# Spec: the model routing table

## Source

Issue #162, body amended before building (recorded in its comment), then
**rewritten against `spec-review.md`**, which returned `changes-requested` with
twelve findings. Five of them changed the design, not its wording. Where this
spec and the issue body disagree, this spec is right and the review says why.

## Tiers, not models

    complex  = ["fable", "opus"]
    standard = ["sonnet"]
    trivial  = ["haiku"]

A tier resolves to the **first model in its chain not declared unavailable**.
`unavailable = ["fable"]` is the state of the subscription today, so `complex`
resolves to `opus`; deleting that one entry is the whole of enabling Fable.

Availability is **declared, not discovered**. A resolver that asks the network
which models exist is not a function of its inputs: it answers differently on
different days, and the Foreman's choice stops being reproducible from the
table. The cost of declaring is a stale entry, which is a wrong answer a human
can see and fix. The cost of discovering is a wrong answer nobody can
reconstruct.

Because that one line is the only edit the design advertises, it is also
validated: **every name in `unavailable` must appear in some tier's chain.**
A transposed `"fabel"` would otherwise leave `complex` resolving to `fable`, at
exit 0, with a confident reason, and the Foreman would start a session against a
model that does not exist.

The tiers are **ordered**: `trivial` < `standard` < `complex`. The order is not
decoration; it is what makes "an override may only escalate" checkable.

## Which stage gets which tier

| Stage | Tier | Why |
| --- | --- | --- |
| `plan` | `standard` | `intent.md` decides what the ticket is |
| `design` | `complex` | a wrong spec is paid for by every later stage |
| `build-planning` | `standard` | the radius is a judgement, but a narrow one |
| `build-implementing` | `standard` | Test, Review and QA sit downstream |
| `test` | `standard` | |
| `review` | `complex` | judging a diff is harder than writing one |
| `qa` | `standard` | reading a Run Report wrong merges a broken bot |
| `document` | `standard` | |
| `integrate` | none | CI decides the merge; no agent runs (#194) |

**`spec-review` is not a stage.** The Specification Reviewer is a role *inside*
`design` (`stages.md` -> Design), and `routing.Stage` has no member for it. Both
of Design's roles resolve to `complex`, so nothing is lost today. If they ever
need different tiers, that needs a role axis and a ticket - not a tenth key that
looks live and is dead.

**`trivial` is reserved and routed to by no stage.** It exists so the tier
vocabulary is complete and so "only escalate" has a floor to be above. A stage
routed to it is a decision to argue in a ticket, not a budget to quietly spend.

## The default, restored

A stage **in the `Stage` vocabulary** but absent from the table resolves to
`standard`, at exit 0, with a reason that says the table did not name it.

The first draft of this spec enumerated every stage and made anything else an
error. The review's objection is the one that decided it: this spec's own
argument is against silent *escalation*, and `standard` can never silently spend
on the strong model. Halting the Foreman over a stage the table forgot - say
whatever #186 does to `document` - is the worse of the two failures.

A stage **outside** the vocabulary is a different thing entirely: that is a
caller asking a nonsense question, and it is an argument error.

## Overrides

    [[overrides]]
    when = { method_live = true }
    use  = "complex"

An override names facts and a tier. **It beats the stage table**, a multi-key
`when` is **AND**, and when several match **the first in file order wins** - the
same rule `factory next` uses, for the same reason: a reader must predict the
answer from the file without ranking overrides by how specific they look.

An override may only name a tier **strictly above** the stage's. A table that
routes *down* is a table error. The first draft stated this as an invariant and
enforced nothing, so `use = "trivial"` on a live ticket's Review would have run
Haiku at exit 0, with a reason proudly naming the rule.

### Facts are a closed vocabulary, computed from the chain

| Fact | True when | Knowable from |
| --- | --- | --- |
| `method_live` | `spec.md`'s `method` is `live` **or** `both` | stage 3 onward |

It covers `both` as well as `live`, matching `chain.needs_qa`. Otherwise a
`method: both` ticket would get `standard` at Review where an identical `live`
ticket got `complex` - the same ticket, two models, for a distinction that means
nothing here.

Two things that look alike and are not:

| | Means | Answer |
| --- | --- | --- |
| A fact **name** the vocabulary does not hold | the table is wrong | table error |
| A known fact **not yet knowable** here | the chain has not got there | does not fire, exit 0 |

The first draft conflated them and shipped three overrides whose facts could not
be evaluated at all, so every call on every ticket would have errored. The
distinction is the fix.

**`touches_hard_stop` does not ship.** It is the body's main complexity signal
and it cannot be computed yet: the radius lives in `plan.md`, which is the
*output* of stage 3, so at `plan`, `design` and `build-planning` the fact is not
unknown but unknowable - and the hard-stop list itself is prose in `AGENTS.md`,
hand-duplicated in `merge.py`, which `merge-policy.md` already says drifts and
which #143 owns. Shipping the mechanism with one override that works beats
shipping three that cannot fire. **Consequence to accept knowingly:** a ticket
touching `docs/adr/**` or the input path gets `standard` at Build today.

**No caller-supplied facts.** Nothing takes a `--fact` flag. An agent that can
pass `escalated = true` has chosen its own model through one indirection, which
is the whole failure this ticket exists to prevent. `escalated` arrives with
#160, sourced from the Foreman's own state.

**Labels are out of scope.** The body's `type:grilling` test is a GitHub label,
and reading one needs `gh` - which breaks "pure and offline" (`intent.md`). The
complexity it stands for is already carried by `design` and `review` being
`complex`.

### Comparison

A fact's value is compared after the stripping `routing.verdict_of` does -
whitespace **and** surrounding quotes, lowercased. `chain.front_matter` does not
strip quotes, so `method: "live"` would otherwise never match and the override
would silently never fire.

## Exit codes

The first draft made every malformed input `MISUSE`. That contradicts
`exit_codes.py`, where `MISUSE` is "wrong arguments, or the wrong stage for this
command" and `NEEDS_HUMAN` is "stop, comment on the ticket, hand back" - and it
contradicts the house precedent, since `cli.py` maps `MalformedVerdict`, the
closest analogue, to `NEEDS_HUMAN`. It also left the Foreman unable to tell a
nonsense question from a broken table, when the remedy differs completely.

**Argument errors - `MISUSE` (2).** The caller asked wrongly:

- a `--stage` that is not a member of `routing.Stage`, `maintain` included
  (documented in `stages.md`, absent from the enum, owned by no role)
- no ticket on the branch and no `--stage`

**Table errors - `NEEDS_HUMAN` (3).** The maintainer's file is wrong, and only
the maintainer can settle it:

- `configs/factory-models.toml` missing, unparseable, or missing a required block
- a tier named by a stage or an override that `[tiers]` does not define
- a tier whose every model is declared unavailable, or whose chain is empty
- a key in `[by_stage]` that is not a member of `routing.Stage`
- a name in `unavailable` that appears in no tier's chain
- a `when` naming a fact outside the vocabulary, or an empty `when`
- an override naming a tier not strictly above the stage's

**No error path resolves to a model.** A silent fallback to `opus` turns a typo
into a bill, which is the one error class this repo has no test for. Note that
the bill argument justifies *refusing*, not any particular code - the codes
above come from the contract.

## The command

`factory model [ticket] [--stage STAGE]`.

- `--stage` asks directly. The ticket form is a convenience that calls
  `routing.resolve` and uses the stage it returns.
- **`integrate` answers `model: null` at exit 0**, with a reason naming CI. The
  first draft made it `MISUSE`, which forced the Foreman to special-case
  `integrate` *before* calling - that is, to already know the thing the resolver
  refused to tell it. A definite "nobody runs this" is an answer, not a refusal.
- A **blocked chain** (`resolve` returns no stage with `blocked_by` set) exits 3
  and carries `blocked_by` through, so the Foreman reports the chain's reason
  rather than a model's.
- A **non-ticket branch with no `--stage`** is `MISUSE`: there is no stage to
  answer about.

`--json` and prose come from one payload, which `cli.py` makes structural for
every registered command. That is not a criterion worth claiming credit for;
what the criteria pin is that the **rule that fired** appears in the payload, so
a human can ask why a stage got the model it got.

## Recording the choice

The resolution carries a `record` line of contracted shape:

    model: <alias>  # tier=<tier>, rule=<rule>

`artifacts.md` reserves the field name `model` so nobody invents a second
spelling. **This ticket does not write it, and does not claim a file carries
it.** Four of the nine stages that get a model have nowhere to record one
today: stage 4's artifact is the diff, stage 5 has no artifact, and `review.md`
and `qa.md` have no contracted front matter until #152. Where the line lands is
#159's decision, when there is a Foreman to write it.

## The table's home

`configs/factory-models.toml`, resolved from the repo root like every other
chain read, with the path injectable so tests can supply one.

Not inside the package: `pyproject.toml` declares no `package-data`, so a
`.toml` under `factory/` is not installed and every call on a non-editable
install would fail - and fixing that means editing `pyproject.toml`, a
**hard-stop path**, which would stall this ticket at stage 3 for scope approval.
`configs/` is also where this repo already keeps settings a human edits, which is
what `intent.md` asked for. Side effect worth having: `configs/` is not in the
merge policy's `allowed_paths`, so a change to the model table can never
auto-merge.

TOML, read with stdlib `tomllib`: `factory` declares no runtime dependencies on
purpose, pinning one is a maintainer decision, and the rationale comments are
half the table's value - which rules out JSON.

## The merge policy

`factory/models.py` joins `POLICY.protected_paths` and `merge-policy.md`'s list,
because `test_merge.py` computes the console script's transitive import closure
and goes red when a module joins it unlisted.

The `.toml` does **not** join that set. `merge-policy.md` defines it as "the
policy, or anything its verdict depends on", and the merge verdict does not
depend on the model table; widening the definition needs an argument this ticket
does not have. It needs no protection anyway - `configs/` cannot auto-merge.

## Radius

Named in `plan.md`, not here.

## What this does not do

- Does not start a session, pass a `--model` flag, or know how a harness is
  invoked. #159 does.
- Does not verify any model alias is real. It cannot: see `intent.md`.
- Does not handle **runtime** availability failure - a worker that asked for
  Fable and could not get it. The body's bullet reads that way; this resolver
  handles only *declared* unavailability, and falling forward at runtime is
  #159's.
- Does not write artifacts, and does not add #160's trust dial.
