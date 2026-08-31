# Decisions and alternatives

Every fork considered so far, the current lean, and what would change the
lean. "Decided" means Nass confirmed it; "lean" means the draft assumes it
but it's open to challenge.

## D1. Fork the repo vs. one repo, two modes — **decided: one repo**

Fork rejected: the shared 95% (movement, minimap, vision, DecisionMakers,
telemetry) is exactly where active development happens; a fork pays a
double-maintenance tax forever. The differing 5% is localized (focus
arbitration, Manager-proxy party state) and sits behind separable seams.

## D2. Coordinator topology — **lean: standing Conductor daemon**

The question Nass asked directly: *"Would the Coordinator be a separate
server that runs permanently, and anyone launching a bot would attach to
it?"* Options weighed:

| Option | Verdict | Why |
| --- | --- | --- |
| **(a) Standing daemon on a bot machine** (chosen) | ✅ | Party lifecycle outlives any Session — Seats at three houses start and stop at different times all day; someone must remember the party across those comings and goings. A daemon is that someone. Single arbiter matches the engine's ethos ("priority is arbitrated in one place"). Hosting on a bot machine is Nass's confirmed constraint — no new hardware. |
| (b) Leader-session (first Session up coordinates) | ❌ | The party dies or thrashes every time the leader's session ends — and sessions end *often* (crashes, map changes gone wrong, manual restarts). Leader re-election across houses adds distributed-consensus complexity precisely where we want none. |
| (c) Peer-to-peer mesh (gossip, no arbiter) | ❌ | Party semantics (one plan, one rendezvous state) inherently want a single writer. P2P buys availability we don't need at a complexity price the scope (≤ 6 seats) never amortizes. |
| (d) Off-the-shelf broker (Redis / MQTT / NATS) as the coordination substrate | ❌ as the architecture, ⚠️ kept as fallback | The hard part isn't moving bytes — it's the party *logic* (membership, plan versioning, rendezvous deadlines), which a broker doesn't provide; it would still live in some process, i.e. option (a) with an extra dependency. If the hand-rolled Conductor's transport layer turns out heavier than expected, swapping its internals to Redis pub/sub is a contained change. |

Caveat accepted with (a): if the Conductor's machine reboots, the party
coordinates nothing until it's back — but every Seat keeps botting in Solo
Fallback, so the blast radius is "no rebuff gathers for a while", not an
outage. That trade is fine at this scale.

## D3. Transport — **lean: Tailscale mesh + plain WebSockets**

Cross-site (2–3 houses) means the internet is in the path.

- **Tailscale (WireGuard mesh) recommended**: NAT traversal for free (no
  port-forwarding at friends' houses — the operationally painful bit),
  encryption + device auth handled below the app, stable virtual IPs, and
  the app layer stays plain `ws://` + JSON as if on a LAN.
- Alternative: WSS on a port-forwarded/DDNS host with shared-token auth —
  no third-party dependency, but hand-rolled TLS/auth and router config at
  every house. More moving parts we own for no gain at 6 seats.
- Protocol either way: JSON messages over one WebSocket per Seat,
  versioned envelope `{type, seq, timestamp, seat, corr_id?, payload}`.
  Volume is trivial (~1 Hz positions × 6 seats); latency tolerance is
  seconds (see 01 §Timing), so tens-of-ms internet RTT is noise.

### D3a. Why not a REST API? (asked 2026-08-30)

The Conductor protocol *is* an API — the question is the interaction model.
REST was rejected on shape, not capacity (6 seats × ~1 Hz is trivial either
way):

- Most traffic is **server-initiated** (plan updates, Rendezvous
  transitions, alarm fan-out). REST can't push, so Seats would poll, and the
  poll interval becomes a latency floor on exactly the messages that want
  immediacy — alarms and rendezvous phases.
- **Presence** falls out of a persistent connection for free (drop +
  missed heartbeats); over REST it must be inferred from poll recency —
  the same mechanism, strictly worse.
- The traffic is **event-shaped**, not resource-shaped. Request/response
  still happens where needed (attach, propose) as correlated request/reply
  over the socket — a WebSocket can do REST's job, not vice versa.
- Same-family alternatives (gRPC streaming, MQTT) share the push model and
  would work; plain WS + JSON is the least machinery. A read-only
  `GET /party/status` HTTP endpoint on the Conductor may be added later as
  a human debugging convenience — not part of the architecture.

## D4. Who owns the network connection on a Seat — **lean: Main Process**

Engines connecting to the Conductor directly was rejected: it breaks the
existing symmetry (Main owns every external listener — Discord, proxy,
engine pipes), multiplies connections, and would hand network state to
processes whose job is reading pixels. Main gets one `ConductorListener`
task; party traffic reuses the existing Engine pipes. DecisionMakers stay
transport-blind.

## D5. Interface altitude — **lean: domain verbs, not distributed primitives**

Rejected: exposing network-backed `Lock`/`Event`/dict lookalikes so
`rebuffs.py` runs unmodified. Distributed locks are the wrong primitive over
a flaky link (who holds a lock whose holder vanished?), and the lookalike
would faithfully reproduce today's implicit state machine instead of making
it explicit. Chosen: `PartyServices` speaks `propose_rendezvous` /
`report_arrived` / `raise_alarm`; the *local* backend maps those onto
today's Manager primitives, the *remote* one onto messages. Decision logic
ports once and stops caring.

## D6. Reads vs. writes — **lean: snapshot reads, event writes**

DecisionMakers read a locally-cached Party Snapshot (instant, stale-tolerant)
and emit fire-and-forget Party Events upstream. Rejected: synchronous RPC
from decide cycles — it would put network round-trips inside the decide loop
and hand every DM a new failure mode. Staleness is already the norm (minimap
reads are seconds-scale); the design leans into it.

## D7. Where the Discord console lives — **lean: Conductor, later**

Target state: one party-scope Discord bot hosted by the Conductor (one
token; today's one-bot-token-per-session model doesn't survive six
concurrent sessions cleanly). Interim: per-session Discord stays exactly as
is; console consolidation is its own late phase (05, phase 6) because
nothing else depends on it.

## D8. Fate of multi-client — **decided: retire eventually**

Confirmed by Nass. Consequences drawn in the draft: `LocalPartyServices`
keeps single-machine parties working through the migration; the focus
machinery is left dormant (not deleted) until a dedicated retirement phase
with its own ADR; no *new* feature targets multi-client.

## D9. Naming — **lean: Conductor / Seat / Party Plan / Rendezvous**

"Coordinator" avoided as too generic (per `CONTEXT.md`'s discipline of one
distinctive term per concept). Glossary drafts live in 02 and graduate to
`CONTEXT.md` with the ADR. Open to bikeshedding exactly once, at ADR time.

## D10. Scope guards

Out of the target scope by Nass's answer: cross-machine leech roles, shared
consumables/economy. The design must not preclude them — both fit as new
Rendezvous purposes / Party Event kinds and new roles on the Party Plan —
but no code, message type, or plan field is added for them now.
