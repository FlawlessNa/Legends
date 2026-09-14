# Precision-movement taxonomy

Resolved by [#11](https://github.com/FlawlessNa/Legends/issues/11) on the
movement map ([#6](https://github.com/FlawlessNa/Legends/issues/6)). Cite rows
by stable id (`PM1`, ...); rows are added, never renumbered. Vocabulary
(**Precision movement**, **Attempt**, **Attempt budget**) is defined in
`CONTEXT.md`; this document holds the enumeration, the tiers, and the budgets —
the pass/fail definitions the telemetry analysis
([#12](https://github.com/FlawlessNa/Legends/issues/12)) and calibration Trials
target.

## What qualifies

A precision movement is a property of a **Movement Plan transition** — the
component, its upcoming component, and landing/departure flags — never of a
movement type alone or of the grid. The same `JUMP_RIGHT` is precision onto a
4 px perch and not across open ground. `ENTER_PORTAL` is the one near-exception
(precision wherever it occurs), carried as a transition row like the others.

## The rows

| Id  | Precision movement | Plan signature | Tier | Classifiable from the Plan today? |
|-----|--------------------|----------------|------|-----------------------------------|
| PM1 | Jump onto rope/ladder | `JUMP_*` → `CLIMB_UP` | Tight | Yes — transition pair |
| PM2 | Landing on a narrow platform | `JUMP_*` or `TELEPORT_*` with `narrow` flag | Tight | Yes — jumps and teleports both |
| PM3 | Edge departure — jump/teleport from a platform's edge, where overshooting the approach is a fall | `JUMP_*` / `TELEPORT_*` with `edge_departure` flag | Tight | Yes — transition pair |
| PM4 | Portal entry | `ENTER_PORTAL` | Routine (*provisional*) | Yes |
| PM5 | Ladder grab from walk | `WALK_*` → `CLIMB_UP` / `CLIMB_DOWN` | Routine (*provisional*) | Yes |

Priority order for building attribution: PM3 and PM2 first (owner-ranked most
important — a PM3 miss is a fall, the costliest and most bot-visible failure),
then PM1, then the provisional rows. *Provisional* means the row may be dropped
without renumbering if attribution shows it succeeds at ~100% first-try; do not
build tooling for provisional rows before the definite ones.

The model gaps (PM2's teleport half, PM3 entirely) were closed by
[#129](https://github.com/FlawlessNa/Legends/issues/129): `narrow` now applies to
`TELEPORT_*` connections as well as `JUMP_*`, and a new `edge_departure` flag on
`_MovementComponent` marks a start node within `edge_departure_threshold` minimap
px (default 5, a **Knob** on `MovementHandler`, mirroring `narrow_platform_threshold`'s
shape) of its platform's end in the travel direction. The precision pre-stop
(direction-key release ahead of the gesture) now fires on that flag unconditionally,
not only when truncation happens to land there. Grid-baked flags were rejected —
every map would need re-authoring and nothing could be swept.

## Tiers and budgets

A tier is a **budget class only** — transitions grouped because the same number
of misses is tolerable. Tiers carry no positional tolerance; tolerances are
per-map-scale measurements and belong to calibration
([#117](https://github.com/FlawlessNa/Legends/issues/117) /
[#120](https://github.com/FlawlessNa/Legends/issues/120)).

| Tier | Rows | Pass | Fail |
|------|------|------|------|
| **Tight** — a miss or two is normal and human | PM1, PM2, PM3 | success within 1–3 Attempts | > 3 Attempts |
| **Routine** — should nearly always land first try | PM4, PM5 | success within 1–2 Attempts | > 2 Attempts |

Budget semantics:

- **Per instance.** One instance of a precision transition (this rope, this
  route cycle's pursuit of it) passes or fails on its own Attempt count;
  instances are never averaged into a rate before judging.
- **Expectations, not Invariants.** Nothing offline can decide them; the
  offline analyzer reports violations, the lab suite never gates on them.
- **Both targets at once.** The budget is the efficiency target and the
  humanization target — a budget overrun *is* the bot-like signature, so one
  flag serves both.
- **Revisable.** The numbers are judgment targets set ahead of data; revise
  them when #12's analyzer and the first Trial campaigns produce real
  per-row distributions. Revising a budget is editing this table, not the
  analyzer.
- **Live reaction is out of scope.** Reacting in-game to repeated misses is
  Stuck / Reaction Ladder territory
  ([#119](https://github.com/FlawlessNa/Legends/issues/119)); the budget is an
  offline judgement only.

### PM3's fall outcome

A PM3 miss is not a retry-in-place: the character falls and must climb back. It
counts as a failed Attempt like any other, but carries a distinct **fell**
outcome on the Attempt record, so the analyzer can weight falls separately
without a third tier. Promote PM3 to its own stricter tier only if the data
shows falls deserve their own budget.

## Success criteria per row

Gesture-level targets for #12 to operationalize against position history; the
detection rules themselves are #12's to define.

- **PM1**: the character is on the rope/ladder — position snaps to the rope
  column and subsequent samples move vertically along it.
- **PM2**: position lands within the narrow platform's span and remains on it
  (no immediate walk-off or fall).
- **PM3**: the character arrives on the target platform without falling; a
  drop below the departure platform's level before the gesture is a **fell**
  outcome.
- **PM4**: the discontinuous position change to the portal's destination.
- **PM5**: vertical movement begins on the ladder column.

## Handoff to #12 (attempt detection)

Requirements this taxonomy imposes on the delimitation rules:

1. **Delimitation is "next gesture at the same transition", never "next
   cycle".** Attempts at one transition can be separated by unrelated recovery
   movement — after a PM3 fall the climb back up is not part of any Attempt,
   and the prior failed Attempt must still be remembered and counted against
   the same instance's budget.
2. **Attribution keys off plan-time flags.** PM2/PM3 classification requires
   the flags #129 adds to reach the telemetry a cycle emits; do not
   re-derive edge/narrow geometry offline.
3. **Per-row success detection** per the criteria above, each decidable from
   position history plus the Plan.
