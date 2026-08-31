# Brief: what we are designing and why

## The shift

The engine was built on the assumption that several game clients run on one
machine and must share keyboard focus. That assumption is ending, for two
reasons:

1. Target private servers may disallow multi-clienting.
2. The interesting scaling axis is now **several machines, one client each**,
   coordinating as an in-game party — split map rotation, gathering to share
   party buffs, moving between maps as a group.

## Decision already made (conversation, 2026-08-30)

**No fork.** One repo serves both worlds. Rationale: ~95% of the code
(movement compilation, minimap model, vision, DecisionMakers, telemetry) is
identical in both; the multi-client assumption is localized to focus
arbitration and the Manager-proxy shared state. The two scenarios are two
configurations of one system once "how many clients does this machine host"
and "how do bots share party state" are separated into orthogonal concerns.

## End-goal criteria (verbatim intent from Nass)

- **Strong and flexible** — a real architecture, not a bolt-on.
- **Doesn't destroy the current single-machine architecture** — it must keep
  working throughout the migration.
- **Simplifies where possible** — e.g. with one client per machine there is no
  keyboard-focus contention on any machine, so the focus-arbitration machinery
  should eventually fall away rather than be dragged along.

## Confirmed constraints (Nass, 2026-08-30 — see 04-open-questions.md)

| Question | Answer |
| --- | --- |
| Scale & network | **≤ 6 machines** across **2–3 physical locations** (Nass's house + 1–2 friends' houses, 1–3 laptops each). Cross-site ⇒ internet transport, auth required, latency in the tens of ms. |
| Coordinator hosting | A **standing service on one of the bot machines** (not a dedicated VPS/Pi, not a leader-session). |
| Fate of multi-client mode | **Eventually retire.** Must not break during migration, but no new features target it, and the focus-sharing machinery gets simplified out once multi-machine matures. |
| Party mechanics in scope | Baseline (**split rotation** + **gather-for-party-rebuff**) plus **coordinated map/channel changes** and **party-wide failsafes**. Explicitly *out* of the target scope: cross-machine leeching roles, shared consumables/economy — design should not preclude them, but nothing is built for them. |

## Non-negotiables inherited from the existing architecture

These come from `docs/ARCHITECTURE.md`, the ADRs, and `AGENTS.md`; the
proposal must not silently contradict them:

- **Only Main Process may press a key** (enforced by crash). Extends naturally:
  only *this machine's* Main Process presses keys into *this machine's* client.
  Nothing arriving over the network is ever a keystroke.
- **ADR 0002**: movement compiles at dispatch, inside the focus-lock critical
  section, against the Held-Keys Ledger. The multi-machine layer must never
  insert a network wait inside that critical section.
- **ADR 0001**: the telemetry envelope has external consumers — changing it
  (e.g. adding a machine/seat identifier) requires explicit sign-off, never a
  drive-by.
- **Dependency direction**: `maple` imports `botting`, never the reverse. Any
  new coordination code must slot into this (see 02 §"Where the code lives").
- **Vocabulary discipline** (`CONTEXT.md`): new concepts get one term each,
  with rejected synonyms listed. Draft glossary entries are in 02 §"New
  domain vocabulary".
