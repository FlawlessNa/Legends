# Migration path

Phased so that single-machine behaviour survives every phase until the
deliberate retirement at the end, and so that each phase delivers something
usable on its own. Phases 1–2 are pure wins even if the multi-machine idea
were later abandoned.

Ticket discipline: each phase becomes issues under a wayfinder map (the
repo's existing pattern). Constants that need measuring against real links
or clients are Expectations → `ready-for-human`, per
`docs/agents/triage-labels.md`.

## Phase 0 — ADR

Converge this research into **ADR 0003** (Conductor/Seat architecture, the
authority split, the no-network-in-the-action-path rule) and graduate the
new vocabulary into `CONTEXT.md`. Nothing ships; the decision stops being
implicit.

## Phase 1 — Extract the `PartyServices` seam *(pure refactor)*

Define the interface in `botting/party/`; implement `LocalPartyServices`
over today's Manager proxies; port `PartyRebuff` (and the shared-dict
choreography in `rebuffs.py`) onto it. Existing suite passes untouched —
that's the refactor gate, per `AGENTS.md`. Single-machine multi-client
behaviour is byte-identical.

## Phase 2 — Single-client mode *(immediate standalone value)*

A config flag declaring "this Session hosts one client". Focus arbitration
becomes trivially satisfied (lock uncontended, no switches; ledger
reconciles only at session start). No deletion — the multi-client path
stays. **This alone enables botting on a no-multi-client private server,
one machine, before any networking exists.**

## Phase 3 — Conductor v0: presence and visibility

The `conductor/` daemon: protocol, attachment, heartbeats, Party Snapshot
push. `ConductorListener` in Main; snapshots flow to `BotData.party` over
the existing pipes. No plan logic, no rendezvous — success criterion is two
machines at two houses seeing each other's positions in their snapshots,
plus Solo Fallback (kill the Conductor, nothing stops). Protocol and
presence logic get offline tests; the cross-house link is verified by hand
and reported as such.

## Phase 4 — Party Plan: split rotation

`maple/party/planner.py` computes region assignments from map-config
features; the Conductor versions and publishes plans; `Rotation` consumes
its assigned region from the snapshot. Rebalance on membership change.
First truly coordinated behaviour, and it's the latency-insensitive one.

## Phase 5 — Rendezvous: rebuff, then travel

The Rendezvous state machine in the Conductor; `RemotePartyServices` grows
the propose/arrived/done verbs; `PartyRebuff` runs over it (`purpose=rebuff`).
Then the staged variant for coordinated map changes (`purpose=travel`),
including the new-map replan. Party-wide failsafe broadcast rides the same
event bus and lands here too (local-first action is already the existing
behaviour; only the broadcast is new).

## Phase 6 — Console consolidation

Party-scope Discord bot moves into the Conductor; per-Seat Peripherals keep
recording and evidence screenshots. Until this phase, per-session Discord
keeps working unchanged.

## Phase R — Retirement of multi-client *(its own ADR)*

Only after the party has hunted reliably for a while: delete
`SharedResources.focus_lock` and decorators, `non_focused_inputs.py`, the
focus-switch reconciliation, the `BlockInput` dance; collapse `activate()`;
degenerate bot grouping (one Bot, one Engine per Session); amend ADR 0002's
assumptions. `LocalPartyServices` survives if single-machine *single*-client
sessions still want party-less operation; the multi-client focus machinery
does not.

## Standing verification caveat

Phases 3–6 all contain behaviour with no offline proof (real gathering,
latency, party dynamics). Offline tests cover protocol logic, state
machines, planners, and compilation invariants; every phase report must
name what was left unverified, per the repo's reporting rule.
