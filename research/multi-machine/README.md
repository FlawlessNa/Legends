# Multi-machine architecture research

Working notes for the decision to evolve Legends from single-machine
multi-client (focus sharing between clients on one PC) toward **multi-machine
single-client** (one client per machine, several machines coordinating as an
in-game party).

This directory is a **brainstorming trace, not documentation**. It is committed
so any agent or human can resume the session at any point. When the direction
is settled, the outcome graduates into an ADR under `docs/adr/` and this
directory's content is superseded — nothing outside this directory may cite it
as authority.

## How to resume this session

1. Read [00-brief.md](00-brief.md) — the goal and the constraints the human
   has already confirmed. Do not re-ask what is answered there.
2. Read [01-current-architecture-facts.md](01-current-architecture-facts.md) —
   the load-bearing facts about today's engine, with file references, so you
   don't re-derive them.
3. Read [02-proposed-architecture.md](02-proposed-architecture.md) — the
   current best proposal. Challenge it; it is a draft.
4. [03-decisions-and-alternatives.md](03-decisions-and-alternatives.md) holds
   every fork in the road considered so far, with the current lean and why.
5. [04-open-questions.md](04-open-questions.md) — what is answered (and by
   whom) vs. still open. Add new questions there; never delete answered ones.
6. [05-migration-path.md](05-migration-path.md) — the phased route from today's
   codebase to the target, designed so single-machine behaviour survives every
   phase until deliberately retired.

## Status

- **2026-08-30** — Directory created. Spec questions answered by Nass (see
  04). First full proposal drafted: standing Conductor daemon on one bot
  machine, sessions attach/detach, party state arbitrated in one place,
  no keystroke ever depends on network liveness. Not yet reviewed by the
  human in detail. Next step: review → converge → write ADR 0003.
