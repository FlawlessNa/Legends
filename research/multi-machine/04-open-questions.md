# Open questions

Append new questions; never delete answered ones — the answers are the spec.

## Answered (Nass, 2026-08-30)

1. **Scale & network?** → ≤ 6 machines, 2–3 locations (Nass's house + 1–2
   friends' houses, 1–3 laptops each). Cross-site internet links are part of
   the normal case, not an edge case.
2. **Where does a standing coordinator live?** → On one of the bot machines.
   (Not a VPS/Pi, not a leader-session.)
3. **Fate of single-machine multi-client mode?** → **Eventually retire.**
   Keep it unbroken during migration; simplify the focus machinery out once
   multi-machine is mature.
4. **Which party mechanics are in the target scope?** → Baseline (split
   rotation, gather-for-rebuff) **+ coordinated map/channel changes +
   party-wide failsafes**. Out: cross-machine leeching, shared
   consumables/economy (don't preclude, don't build).

## Open — needs Nass

- **O1. Telemetry across the party** (touches ADR 0001 — must not be decided
  silently): should Party Events also land in each Seat's `telemetry.jsonl`,
  and should the envelope gain a `seat` field so offline analyzers can merge
  six machines' records into one party timeline? Analyzer compatibility is
  the constraint.
- **O2. Failsafe policy matrix**: per alarm kind (GM test, stranger in map,
  character moved, client crashed), what does the *rest* of the party do —
  pause, logout, scatter, ignore? Needs Nass's judgment about the target
  server's moderation behaviour; the architecture just carries the policy.
- **O3. Conductor machine identity**: which machine hosts it in practice
  (the always-on desktop at Nass's house?), and does it also run a Seat?
  (Design assumes "yes, may also run a Seat"; loopback attach is the same
  code path.)
- **O4. Region-splitting inputs**: is minimap-feature granularity (the JSON
  map configs' feature list) the right partition unit, or do some maps need
  finer splits (e.g. one long platform shared between two hunters)? Likely
  answerable only by watching real maps — flag as `ready-for-human` when it
  becomes a ticket.
- **O5. Start gate**: do Seats need a synchronized start (today's launch
  Barrier, cross-machine), or is "attach whenever, plan rebalances" enough?
  Draft assumes the latter.
- **O6. Tailscale acceptable?** It's a third-party dependency with accounts
  at friends' houses; the alternative (WSS + port forwarding + DDNS) trades
  that for router configuration. Draft assumes Tailscale.
- **O7. In-game party invites**: forming the actual in-game party (invite,
  accept) is an interface interaction. In scope for automation, or done by
  hand at session start? Draft assumes by hand initially.

## Open — technical, resolvable by an agent later

- **T1.** Exact `PartyServices` signatures once `rebuffs.py` is actually
  ported (the draft protocol in 02 is illustrative, not final).
- **T2.** Heartbeat/suspect/rebalance timings — Expectations in the
  CONTEXT.md sense (need measurement against real links), so the constants
  must live in config, not code.
- **T3.** Whether `LocalPartyServices` implements Rendezvous with today's
  Lock+Event or with a small in-process state machine mirroring the
  Conductor's (lean: the latter — one semantics, two transports).
- **T4.** Conductor persistence: does it need to survive its own restart
  with state intact (party roster on disk), or is "Seats re-attach and
  rebuild" enough? Lean: stateless restart + re-attachment.
- **T5.** Protocol testing story: the Rendezvous state machine and plan
  versioning are pure logic → offline pytest (Invariant-style). What cannot
  be verified offline: real gathering behaviour, latency effects, Tailscale
  operational quirks. Per repo convention, every phase report must say so.
