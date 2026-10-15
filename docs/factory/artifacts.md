# The artifact chain

One directory per ticket, on the ticket's branch. Each file is markdown a person
reads, carrying YAML front-matter a program reads — so the stage can be computed
from the artifacts themselves rather than from a separate state file.

```
.factory/133/
  intent.md     # what is wanted, why, under which constraints
  spec.md       # requirements, criteria, and the verification method
  plan.md       # tasks, files changing, order, the radius, proof of completion
  tasks/        # per-task records, when the plan declares tasks
  qa.md         # the Run Report -- only when spec.md says the method is live
  review.md     # findings against REVIEW.md
```

It lives on the branch, not in the issue body, for three reasons: the chain
travels with the PR so a reviewer sees intent, spec, plan and evidence in one
diff; hooks read it with no network call; and an edit to the criteria after the
fact shows up in `git log` as what it is. The GitHub issue stays the
human-facing surface and references the commits.

## Front-matter contracts

A parser implements these; `factory spec check` and friends enforce them.
Required fields are required — a missing one is an error naming the field, not a
default.

### `intent.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | The issue number. Must match the directory. |
| `stage` | `plan` | Always `plan`; intent is stage 1's artifact. |
| `accepted_by` | string \| null | Who accepted it. `null` until accepted. |
| `accepted_at` | date \| null | When. |

Body sections, all required, empty ones marked rather than omitted: problem
statement, proposed outcome, affected users and systems, constraints, open
questions.

### `spec.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | Must match the directory. |
| `stage` | `design` | |
| `method` | `suite` \| `live` \| `both` \| `assent` | **What settles it.** The field the whole factory turns on. |
| `criteria` | list of strings | Each one decidable. See below. |
| `specified_by` | string | Who wrote the criteria. |
| `specified_at` | date | |
| `reviewed_by` | string \| null | The Specification Reviewer's verdict. `null` blocks stage 3. |

**`spec.md` does not carry the radius.** That lives in `plan.md`. The radius is
an implementation fact nobody knows until the code has been read, and if it
lived here the Builder would eventually need to edit this file — and a Builder
that can write to `spec.md` at all can soften the criterion it is judged against.

**A criterion must be decidable.** Could two honest people disagree about
whether it was met? Then it is not a criterion yet. "Works correctly" fails;
"`pytest -m lab` reports 23 selected" passes.

**For `method: live`**, the criteria must additionally name the schedule, the
metric and the number — all fixed *before* any run. An agent handed both the
data and the authority to pick the bar will fit one to the other, honestly and
unconsciously.

### `plan.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | |
| `stage` | `build` | |
| `radius` | list of globs | **The only paths Build may touch.** |
| `tasks` | list \| null | Each with `id`, `radius`, and `parallel`: true/false. |
| `merge_order` | list \| null | Required when any task is parallel. |
| `proof` | object | `red_test`, `red_output_sha`, `suite` — filled at stage 5. |
| `docs_cleared` | list \| null | Coupled documents needing no change, each with a reason. |

### `qa.md` and `review.md`

`qa.md` is written only when `method` is `live` or `both`. It must name the
schedule, the **commit** it ran against, the number of trials, the measured rate
against the criterion, and the defects counted. **A Run Report that does not name
a commit is not evidence — it is a story about a different build.**

## Tickets and tasks

`plan.md` may declare tasks, and several Builders may work them in parallel
worktrees. **Tasks do not get tickets or chains of their own.**

A ticket is the unit of *acceptance*; a task is the unit of *work*. A ticket has
a `spec.md` — criteria and a method, written by someone who is not the Builder.
A task inherits them and cannot be judged done on its own, only finished. Task
records nest under `tasks/` and carry no `criteria` and no `method`.

**If a task needs its own `spec.md`, it is a ticket, and the split happened at
the wrong stage.** Splitting belongs at Design, where criteria are written, not
at Plan, where work is divided. Three signals mean a slice was really a ticket:
it needs a different verification method from its siblings, it touches a
hard-stop path while they do not, or it could merge alone and still be worth
something.

One ticket, one spec, one PR. Parallel worktrees merge into the ticket's own
branch in the order `plan.md` states — never into the trunk independently.
