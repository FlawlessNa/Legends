# Offline invariant catalogue — movement

Closed catalogue of the properties the offline movement lab checks. Resolves
[#9](https://github.com/FlawlessNa/Legends/issues/9).

Vocabulary is `CONTEXT.md` -> **Movement compilation** and **Movement checking**:
Path, Movement Plan, Input Sequence, Action, Step, Hold, Delivered Prefix,
Invariant, Expectation, Continuation, Preemption. Cite entries by their id (A3,
D1, ...) — the ids are stable.

## Notation

For an Input Sequence `S` of Steps `s0..s(n-1)`:

- `H0` — the keys held entering `S` (`initial_held_keys`, or the live query when absent).
- `t(i)` — elapsed time at which Step `i` is sent: sum over `j < i` of `delays[j] + OVERHEAD`.
- `down(i)` — the set of keys down immediately after Step `i`, accumulated from `H0`; `down(-1) = H0`.
- **Hold** — `(key, t_down, t_up)`, half-open over `[t_down, t_up)`; `t_up` is the sequence end when the key is never released.
- `D(k)` — the Delivered Prefix ending at Step `k`: Steps `s0..s(k-1)` plus the forced-release volley.
- Direction keys are `left`, `right`, `up`, `down`; every other key is non-directional.

Two tiers. **Invariant**: absolute, decidable offline with no measured constant,
violation is a defect, gates the suite. **Expectation**: tolerance-bound or
dependent on constants measured from the live game, reported not gating.

## A — Input Sequence, structural

Checked on every compiled Input Sequence.

| Id | Statement | Tier | Status |
|---|---|---|---|
| **A1 Shape** | `len(keys) == len(events) == len(delays)`; at each Step, `keys[i]` and `events[i]` are both `str`, or both `list` of equal length | Invariant | holds |
| **A2 Terminal Release** | If `S` was not truncated, `down(n-1)` is a subset of `forced_key_releases` | Invariant | fails — [#25](https://github.com/FlawlessNa/Legends/issues/25) |
| **A3 No Opposing Overlap** | No Hold of `left` overlaps a Hold of `right`; likewise `up`/`down` | Invariant | holds |
| **A4 Skill Key Closure** | Every Hold whose key is non-directional has `t_up` strictly before the sequence end | Invariant | holds |
| **A5 Delays** | Every delay is finite and `>= 0` | Invariant | holds |
| **A6 No Phantom Release** | For every keyup of key `k` at Step `i`: `k` is in `down(i-1)` | Invariant | fails — [#28](https://github.com/FlawlessNa/Legends/issues/28) |

**A6** is a humanization property as much as a correctness one: a human never
releases a key they are not holding, and the pattern is machine-distinguishable.
It contradicts `_clear_opposites(strict=True)`, whose blind release exists only
because compile-time held-keys state is untrustworthy — so A6 cannot be
satisfied until [#24](https://github.com/FlawlessNa/Legends/issues/24) makes that
state authoritative.

## B — Movement Plan / Input Sequence consistency

| Id | Statement | Tier | Status |
|---|---|---|---|
| **B1 Truncation Integrity** | If `S` is truncated at Step `k`, `k` falls on a Movement Plan component boundary; the cut never lands inside a `JUMP*`, `TELEPORT*`, or `ENTER_PORTAL` component | Invariant | not yet checkable |
| **B2 Fill Bound** | For a walk component of length `L`, the elapsed compile budget spent on it is at least `L/grid.speed` and less than `L/grid.speed + max_delay + OVERHEAD` | Invariant | holds |
| **B3 Distance Fidelity** | The character's actual displacement matches the component's intent within tolerance | Expectation | needs [#13](https://github.com/FlawlessNa/Legends/issues/13)/[#14](https://github.com/FlawlessNa/Legends/issues/14) |
| **B4 Component Non-empty** | Every component up to the cut produced at least one Step, unless its direction was already held at component start | Expectation | holds |

**B1 requires data the Input Sequence does not carry.** A Step has no record of
which Movement Plan component produced it; the compiler knows the boundary and
discards it. Requirement handed to
[#10](https://github.com/FlawlessNa/Legends/issues/10) and
[#15](https://github.com/FlawlessNa/Legends/issues/15): **Steps must carry
Movement Plan provenance.** B1 is unenforceable until they do.

**B2 bounds the elapsed budget, not the Hold.** Release Steps inserted ahead of
a component consume budget without extending the direction's Hold, so the two
diverge. If that gap turns out to matter, it becomes its own entry.

## C — Continuation pair

`N` reached its end, the route-cycle lock released, `N+1` compiled from the
resulting position.

| Id | Statement | Tier | Status |
|---|---|---|---|
| **C1 Inherited State Agreement** | `N+1`'s `initial_held_keys` equals `down` at the end of `N`'s Delivered Prefix, minus the keys the forced-release volley fired on | Invariant | holds |
| **C2 Boundary Opposing Release** | If `N+1` presses a direction whose opposite is in its `H0`, a release Step for that opposite precedes the press | Invariant | holds |
| **C3 No Inherited Stuck Key** | For every `k` in `H0` of `N+1`: either `k` is a direction `N+1`'s first component uses, or `N+1` contains a keyup of `k` | Invariant | holds |

C3 deliberately permits a carried direction key. A route cycle cannot preempt
itself — rotation's Action takes a non-blocking lock released only on task
completion — so every rotation-to-rotation boundary is a Continuation, and
releasing the direction there would reintroduce a stop-start stutter.

## D — Preemption pair

A higher-priority Action from a *different* DecisionMaker cancelled `N`
mid-flight.

| Id | Statement | Tier | Status |
|---|---|---|---|
| **D1 Cancel Safety** | For every cancel point `k` in `[0, n]`, the keys in `down(k-1)` that are not in `forced_key_releases` contain no non-directional key | Invariant | fails — [#26](https://github.com/FlawlessNa/Legends/issues/26) |
| **D2 Preemption Direction Release** | After a Preemption, no direction key remains down | Invariant | holds — fixed by [#27](https://github.com/FlawlessNa/Legends/issues/27) |

**Cancel points are swept exhaustively** — every `k` from `0` to `n`, not
sampled. An Input Sequence is tens of Steps and each check is a set operation
over the already-derived Holds, so exhaustive is cheap and removes "did we
sample the bad index" from every future failure discussion.

**D2 was stated as an outcome, not a mechanism**, because the mechanism was
[#24](https://github.com/FlawlessNa/Legends/issues/24)'s to choose.
`forced_key_releases` cannot express it: it fires from a `finally`, so it runs on
normal completion too, and putting directions in it would force a release at the
end of every Continuation.

[#27](https://github.com/FlawlessNa/Legends/issues/27) settled the mechanism as
#24 predicted it would. The `focused_inputs` send loop releases every direction
key the Held-Keys Ledger holds for the window on its cancellation path only, so
the per-Action `cancel_callback` wiring — which only rotation ever had — is gone,
along with `ActionRequest.cancel_callback` itself. Two properties follow from the
release living in the send loop rather than in a task done-callback: it fires
inside the focus-lock critical section, so it reaches the preempted client rather
than whichever one the preempting Action has meanwhile brought to the foreground;
and it reads the ledger, so it also clears a direction key an earlier
Continuation carried over before this sequence delivered a Step of its own.

## Deliberately excluded

- **"No keyup without a preceding keydown" as accepted behaviour.** Initially
  excluded, because `_clear_opposites(strict=True)` emits exactly that on
  purpose. Reversed: it is now **A6**, an Invariant, on humanization grounds.
- **Movement Plan correctness** — whether pathfinding chose a sensible route, or
  whether a node transition is legal. Real, but a question about
  `path_into_movements`, not about Input Sequences; it belongs to the test corpus
  ticket [#10](https://github.com/FlawlessNa/Legends/issues/10).

## Implementation requirements this catalogue imposes

1. **Hold derivation on `KeyboardInputWrapper`** — a `@property` alongside the
   existing `keys_held`, which already performs the same walk while discarding
   the timing. One traversal, one source of truth;
   `toolkit/movement_timeline._parse_intervals` becomes its body and the Gantt
   tool consumes it.
2. **Movement Plan provenance on Steps** — without it B1 is unenforceable.
3. **The lab constructs Actions, not just Input Sequences** — D1 and D2 are
   about what survives cancellation, which depends on the Action's cancel
   handling.
4. **Compilation parameterised on `H0`** — already delivered by
   [#7](https://github.com/FlawlessNa/Legends/issues/7). Every entry here is
   stated *given* an inherited held-keys set, so the catalogue stays valid even
   if #24 moves held-keys resolution to execution time.
