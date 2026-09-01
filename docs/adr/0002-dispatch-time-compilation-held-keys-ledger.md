---
status: accepted
---

# Live movement compilation moves to dispatch time, fed by a Main-Process Held-Keys Ledger

## Context

Live movement compilation (`MovementHandler.movements_into_action`) runs in
each DecisionMaker's own process at decide time, sampling held keys once via
`GetAsyncKeyState`; the compiled Input Sequence is then pickled to Main
Process, queued, and dispatched later. Two defects compound:

- **Timing gap**: the held-keys snapshot can be stale by dispatch — chiefly
  when another client acts in between, because `SendInput` only reaches the
  foreground window and `activate()` releases every sent key before switching
  focus, wiping this client's held state.
- **Scope bug**: `GetAsyncKeyState` is system-wide; with multiple clients the
  query reads whichever window is foreground, so a DecisionMaker can compile
  against another client's keys.

Held keys shape the *structure* of an Input Sequence — skipped keydowns for
keys assumed held, the `FIRST_DELAY` vs. repeat-delay choice, opposite-key
releases — so a wrong snapshot cannot be patched with a corrective prefix
after the fact. And only Main Process ever knows the
[Delivered Prefix](../../CONTEXT.md): cancellation truncates a sequence at an
arbitrary Step inside its send loop.

## Decision

1. **[Held-Keys Ledger](../../CONTEXT.md)** in Main Process: a per-handle
   record of every key sent and not yet released — all keys, not just
   directions, subsuming the global `SharedResources.keys_sent`. Written at
   Step granularity by the `focused_inputs` send loop, by the forced-release
   block, and by `release_all` on focus switches (clearing the old
   foreground's entry). Reconciled to physical key state at session start and
   at every focus switch — the only places `GetAsyncKeyState` remains; every
   other live query (`get_held_movement_keys(handle)`,
   `Rotation._release_left_right`, forced-release checks) reads the ledger.
2. **Compile at dispatch**: DecisionMakers stop sending compiled Input
   Sequences; an ActionRequest's procedure carries the Movement Plan plus
   compile inputs, and compiles *inside the focus-lock critical section* —
   acquire focus, read the ledger, feed it through the existing
   `initial_state` seam, stream the Steps. Compiling before the lock
   would re-open the same race one layer down. The DecisionMaker decides
   whether to act from its `movements` attribute; the compiled `action`
   attribute leaves the live path (it remains the offline lab's artifact),
   and `_always_release_keys_on_actions`'s transform becomes a flag consumed
   by the dispatch-side compile.
3. **Main-Process-only input guard**: the input-sending functions raise if
   called outside Main Process, converting the architectural rule "all
   keyboard input goes through Main Process" from convention into a crash.

## Consequences

- Both defects die in one data flow, with no reconciliation heuristics. The
  `initial_state` seam built for offline determinism is now also the live
  injection point — fed dispatch-time authoritative state, the opposite of
  the stale-snapshot misuse it was warned against.
- Rejected: *dispatch-time corrective prefix* (approximates what builders
  would have compiled, second code path to keep honest) and *pushing ledger
  state to DecisionMakers* (Main→Engine pushes are awkward here, and a
  residual compile→dispatch race survives).
- Load-bearing assumption: **no key is left down across a focus switch**
  (`activate()` releases before deactivating). This makes the game's
  latching/polling behavior for background windows unreachable, so it never
  had to be empirically characterized.
- Known blind spot: keys pressed by a human on the physical keyboard
  mid-session are invisible to the ledger and only caught at reconciliation
  points.
- Per-instance compile caches stop mattering on the live path; compilation
  (pure list-building) now runs inside the focus-lock critical section,
  which costs microseconds.
- Delivered by #30: `controller.compile_and_send` is the live path's
  ActionRequest procedure. The compile is a picklable callable over plain data
  (`compile_movements`; `cast_skill_compiler` for skill casts) invoked *inside*
  `focused_inputs`, after focus is acquired, so it shares the send loop's
  critical section and its cancellation handling rather than opening a second
  one. `data.action` and `_always_release_keys_on_actions` left the live path,
  the latter surviving as an `always_release` compile flag.
- Central preemption cleanup (releasing directions on cancel from the
  ledger, replacing per-Action `cancel_callback` wiring) becomes possible —
  the mechanism issue #27 anticipated. Delivered by #27: the release sits on
  the `focused_inputs` cancellation path, inside the same critical section,
  and `ActionRequest.cancel_callback` is gone.
