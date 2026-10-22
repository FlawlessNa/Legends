# Roles

> **Supersedes.** The target roles are in [design.md](design.md) §8: designer,
> spec-reviewer, planner, builder, reviewer, orchestrator. The Clerk, the
> Documenter and the Integrator go. These sections change, each when its
> ticket merges:
>
> - The opening role table: #218 (`roles.py`) and #163 (write scopes).
> - "The human's role": #222, where the maintainer accepts the spec and never reads the plan.
> - "Today": #163.
>
> Until then, this page describes today, and it is right about today.


One rule generates all of them:

**The agent that writes the criteria is not the agent that satisfies them, and
the agent that builds is not the agent that judges.**

Separation of powers is the only structural defence against an agent reporting
success it cannot know. Better prompting is not one.

A role is a bundle of three things: a system prompt, a tool allowlist, and a
write scope. Not necessarily a different model, and not necessarily a different
session — though both help.

| Role | Owns stages | May write | May never write | Escalates when |
| --- | --- | --- | --- | --- |
| Clerk | 1 | The ticket body and labels | Code, criteria | The request is too vague to shape |
| Specifier | 2 | Criteria, the method | Code, the diff | No offline or live method can settle it |
| Specification Reviewer | 2 (gate) | A verdict on `spec.md` | Code, the criteria themselves | The intent and the spec do not match |
| Builder | 3, 4, 5 | Code inside the radius, new tests | `spec.md`, the criteria | The work needs a path outside the radius |
| Reviewer | 6 | The verdict, PR comments | Code | The diff does something the spec never asked for |
| QA Operator | 7 | The Run Report only | Any source file | The Session will not start, or the client is not ready |
| Documenter | 8 | Documentation, `docs_cleared` | Code | A coupled document describes something it no longer understands |
| Integrator | 9 | Merge, labels, closing comments | Code | Any gate is missing its artifact |

## Why QA is its own role

If the Builder runs its own QA it will tune the run until it passes: widen a
tolerance, pick a friendlier map, retry until a good sample appears. Each looks
like a reasonable decision. Together they are how a factory produces confident
garbage.

The QA Operator starts from criteria it did not write, runs what the spec names,
and reports what happened. It has no write access to source, so "make it pass"
is not an action available to it.

## Why the Specification Reviewer exists

A gap in `spec.md` is the most expensive error the factory can make and the only
one invisible until QA. The Builder builds to the criteria, QA measures against
them, Review judges by them — a vague criterion is faithfully executed by every
downstream stage while every gate reports green.

It is also the cheapest thing to review: one document, no code, no client.

## The human's role

Three things the factory never takes:

1. **Scope approval** on anything touching the hard-stop paths in `AGENTS.md`.
2. **Owning the machine** and the logged-in client.
3. **Resolving escalations** — and an escalation is *only* one of the four
   kinds listed in [README → Decide and record](README.md#decide-and-record).
   Not "I was unsure". Not "there were two reasonable options". Those are
   decisions, and they belong to whoever is holding the ticket.
4. **Observation** — any answer that can only come from watching the character
   on a running client. A measured constant is the maintainer's, always.

Everything else is delegated **now**, not eventually. An agent that cannot find
an answer in the repo picks the conservative option, records it, and continues
(see [README → Decide and record](README.md#decide-and-record)).

The reason this is stated so sharply: the maintainer's scarcest resource is his
own attention, and a process that routes every uncertainty at him converts a
bottleneck into a standstill. #194 is the worked example — a whole session spent
asking, producing no branch, no artifacts and no PR.

## Today

**[unenforced]** — all of it. One agent currently performs every role, which is
the separation-of-powers hole at the centre of the design. Two things stand in
until #163 and #180 land:

- The maintainer amending a ticket's acceptance criteria before it is claimed,
  which makes the criteria something the Builder did not author.
- A review subagent with no write access, reading the diff against the spec.

Neither is equivalent to the real thing. Do not describe them as if they were.
