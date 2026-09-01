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
| **A2 Terminal Release** | If `S` was not truncated, `down(n-1)` is a subset of `forced_key_releases` | Invariant | holds — fixed by [#25](https://github.com/FlawlessNa/Legends/issues/25) |
| **A3 No Opposing Overlap** | No Hold of `left` overlaps a Hold of `right`; likewise `up`/`down` | Invariant | holds — fixed by [#28](https://github.com/FlawlessNa/Legends/issues/28) and [#97](https://github.com/FlawlessNa/Legends/issues/97) |
| **A4 Skill Key Closure** | Every Hold whose key is non-directional has `t_up` strictly before the sequence end | Invariant | holds — fixed by [#75](https://github.com/FlawlessNa/Legends/issues/75) |
| **A5 Delays** | Every delay is finite and `>= 0` | Invariant | holds |
| **A6 No Phantom Release** | For every keyup of key `k` at Step `i`: `k` is in `down(i-1)` | Invariant | holds — fixed by [#28](https://github.com/FlawlessNa/Legends/issues/28) |

**A6** is a humanization property as much as a correctness one: a human never
releases a key they are not holding, and the pattern is machine-distinguishable.
It contradicted `_clear_opposites(strict=True)`, whose blind release existed only
because compile-time held-keys state was untrustworthy;
[#24](https://github.com/FlawlessNa/Legends/issues/24) made that state
authoritative and [#28](https://github.com/FlawlessNa/Legends/issues/28) removed
the blind release, so opposites are now cleared off real held state alone.

**A3 did not really hold before #28**, despite its status here. The
opposite-key release that `append` inserts was going in at index `-1` — *ahead of* the last existing Step, which is
typically the keydown of the very key being released. A plan reversing direction
compiled to `right keyup, right keydown, left keydown`: a phantom release, and
both directions down after it. #28 moved the insertion to the end of the
sequence, where the release lands immediately ahead of the Step that opposes it.

**A4 did not hold before #75**, and telecast is what made that visible. `teleport`
and `cast_skill` each compiled to a run of skill-key keydowns with no keyup, so the
key's Hold ended at the sequence end and the forced volley in `focused_inputs`'
`finally` was its only release. The latch was not confined to the tail: a
`teleport -> walk` plan held the teleport key down for the whole walk, five seconds
past the component that pressed it.

[#75](https://github.com/FlawlessNa/Legends/issues/75) settled it against the
builders, not the statement. Two readings were open - exempt keys in
`forced_key_releases` (whose release **A2**/**D1** already cover), or fix the
builders - and the exemption would have made A4 strictly weaker than A2 and therefore
worth deleting rather than restating. Spy++ decided it: a released skill key stops
casting while a *held* direction key keeps the character walking, so the sequence a
human produces closes the skill key inside the component and carries only directions
across. Both builders now emit the keyup. `teleport`'s is guarded on the key actually being
down - `fill` stops on absolute sequence duration and can emit no Step at all, and an
unguarded release there would violate **A6**. `cast_skill`'s was guarded for the same
reason until [#98](https://github.com/FlawlessNa/Legends/issues/98) made its keydown
unconditional, which removes the exposure rather than guarding it; see **B5**.

Direction keys stay exempt by design: carrying them across a route-cycle boundary is
what stops the character halting and restarting between actions (the **Continuation**
carry). The `repeat_key` shapes in `teleport` and `single_jump` latch `up` on purpose,
arriving at a rope or portal already holding it.

The forced-release list is unchanged and still declares these keys - it is the
truncation safety net for a cut landing between a keydown and its keyup, which is what
**D1** rests on. It is no longer the normal release path.

Since [#84](https://github.com/FlawlessNa/Legends/issues/84), telecast rebuilds the
teleport region into paired down/up taps and never contributed to A4 anyway.

## B — Movement Plan / Input Sequence consistency

| Id | Statement | Tier | Status |
|---|---|---|---|
| **B1 Truncation Integrity** | If `S` is truncated at Step `k`, `k` falls on a Movement Plan component boundary; the cut never lands inside a `JUMP*`, `TELEPORT*`, or `ENTER_PORTAL` component | Invariant | not yet checkable — mechanism decided by [#10](https://github.com/FlawlessNa/Legends/issues/10) |
| **B2 Fill Bound** | For a walk component of length `L`, the elapsed compile budget spent on it is at least `L/grid.speed` and less than `L/grid.speed + max_delay + OVERHEAD` | Invariant | holds |
| **B3 Distance Fidelity** | The character's actual displacement matches the component's intent within tolerance | Expectation | needs [#13](https://github.com/FlawlessNa/Legends/issues/13)/[#14](https://github.com/FlawlessNa/Legends/issues/14) |
| **B4 Component Non-empty** | Every component up to the cut produced at least one Step, unless its direction was already held at component start | Expectation | holds |
| **B5 Cast Window** | For a `cast_skill` component, the skill key is pressed at least once, and its keyup is *sent* strictly before the first skill keydown plus `animation_time` | Invariant | holds — fixed by [#98](https://github.com/FlawlessNa/Legends/issues/98) |

**B1 requires data the Input Sequence does not carry.** A Step has no record of
which Movement Plan component produced it; the compiler knows the boundary and
discards it. Requirement handed to
[#10](https://github.com/FlawlessNa/Legends/issues/10) and
[#15](https://github.com/FlawlessNa/Legends/issues/15): **Steps must carry
Movement Plan provenance.** B1 is unenforceable until they do.

[#10](https://github.com/FlawlessNa/Legends/issues/10) settled the mechanism:
**Provenance** rides as an `origins` list on `KeyboardInputWrapper`, one Movement
Plan component index per Step, written by `compile_movements` and carried through
`truncate` and telecast's teleport-region rebuild. Chosen over widening
`compile_movements`' return type, which would break the
`Callable[[frozenset[str] | None], KeyboardInputWrapper | None]` compiler seam
that [#30](https://github.com/FlawlessNa/Legends/issues/30) and
[#68](https://github.com/FlawlessNa/Legends/issues/68) both built adapters
against, and over re-deriving boundaries inside the lab, which would reimplement
the compiler in the test that checks it.

Truncation is the normal case, not an edge case: rotation passes
`total_duration=self.data.action_duration` on every Action, so essentially every
movement the bot makes is a truncated Input Sequence. The cut is made on elapsed
time alone — `truncate` copies Steps until the budget is spent and stops wherever
that lands, blind to components. For a walk that is harmless; for a `JUMP*`,
`TELEPORT*` or `ENTER_PORTAL` it splits an atomic in-game gesture.

The compiler *attempts* the mirror-image case - `_PRECISION_PRE_STOP` releases the
horizontal key so the chunk after the cut starts from a stopped position, ahead of
a jump or portal the cut *precedes* - but
[#100](https://github.com/FlawlessNa/Legends/issues/100) showed that release is
inert: it is appended as the last Step and the `truncate` that immediately follows
stops copying once the budget is spent, which it already is on that branch. So
neither half of the truncation problem is handled today. B1 is the half that is
not even expressible without Provenance; #100 is the half that is expressible and
simply broken.

**B5 did not hold before #98**, in both directions at once. `cast_skill` passed
`fill` a raw `skill.animation_time`, and `fill`'s limit is an *absolute* sequence
duration: the direction Steps appended ahead of it were spent out of the cast's own
budget. Every other `fill` call site passes a delta (`teleport`:
`initial_duration + animation_time * num_times`). Given a short enough
`animation_time` the setup exhausted the whole window, the fill emitted nothing, and
the skill was never cast at all — the case that forced the A4 keyup to be guarded.

The other direction is the one observed live: the fill ran *until* the limit and the
keyup was appended after it, so the skill key was still down at the moment the
animation completed and the game's auto-repeat started a second cast.

Both are settled without a measured constant, so B5 is an Invariant rather than an
Expectation. The window is now a delta from where the fill starts, and the fill
reserves one Step's worth of it — `1.05 * DELAY + OVERHEAD`, the most a single filled
Step can cost — so the keyup is sent strictly inside the window. Where the window is
too short to fill at all, the skill key is pressed once regardless: a component that
compiles to no skill Step has silently not cast the skill, which is **B4**'s concern
one level down. That also makes the keydown unconditional, so A4's keyup needs no
guard here and A6 has no exposure to guard against.

**B2 bounds the elapsed budget, not the Hold.** Release Steps inserted ahead of
a component consume budget without extending the direction's Hold, so the two
diverge. If that gap turns out to matter, it becomes its own entry.

## C — Continuation pair

`N` reached its end, the route-cycle lock released, `N+1` compiled from the
resulting position.

| Id | Statement | Tier | Status |
|---|---|---|---|
| **C1 Inherited State Agreement** | `N+1`'s `initial_held_keys` equals `down` at the end of `N`'s Delivered Prefix, minus the keys the forced-release volley fired on | Invariant | holds |
| **C2 Boundary Opposing Release** | If `N+1` presses a direction whose opposite is in its `H0`, a release Step for that opposite precedes the press | Invariant | holds — fixed by [#97](https://github.com/FlawlessNa/Legends/issues/97) |
| **C3 No Inherited Stuck Key** | For every `k` in `H0` of `N+1`: either `k` is a direction `N+1`'s first component uses, or `N+1` contains a keyup of `k` | Invariant | holds — fixed by [#97](https://github.com/FlawlessNa/Legends/issues/97) |

C3 deliberately permits a carried direction key. A route cycle cannot preempt
itself — rotation's Action takes a non-blocking lock released only on task
completion — so every rotation-to-rotation boundary is a Continuation, and
releasing the direction there would reintroduce a stop-start stutter.

**C2 and C3 did not hold before [#97](https://github.com/FlawlessNa/Legends/issues/97)**,
despite their status here — and neither did **A3**, a second time, for a different
reason than #28's. All three read `KeyboardInputWrapper.keys_held`, which walked the
Steps from an *empty* set instead of from `H0`, so it reported `down(n-1)` only for
keys the sequence itself had pressed. `_resolve_held_keys` returns that property
whenever a structure already exists, which is every builder after the first, so the
Held-Keys Ledger's state reached the first builder and was then dropped.

A direction inherited and not re-pressed by the first component was therefore
invisible for the rest of the compile: the end-of-sequence release never released it
(C3), and `append` never cleared it as an opposite, so a later `left` keydown went in
with `right` still down (C2, and both horizontals held at once — A3). #97 seeds the
property from `initial_held_keys`, which is what `down(-1) = H0` says it always meant.

The carry C3 permits is unaffected: it happens on **truncation**, where the
end-of-sequence release does not run at all.

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

## E — Movement Plan structure

Checked on every Movement Plan compiled from a sampled `(start, end)` pair. These
are properties of `path_into_movements` and of pathfinding, not of an Input
Sequence — the layer [#9](https://github.com/FlawlessNa/Legends/issues/9)
deliberately excluded and handed to
[#10](https://github.com/FlawlessNa/Legends/issues/10), which brought it back as
its own group rather than as ad-hoc asserts in the lab.

| Id | Statement | Tier | Status |
|---|---|---|---|
| **E1 Path Terminus** | For a pair the grid reports reachable, the Path is non-empty and its last node is the requested end | Invariant | not yet checked |
| **E2 Adjacency Legality** | Every consecutive node pair in a Path is a grid neighbour or a declared connection — `path_into_movements` reaches neither of its `NotImplementedError` branches | Invariant | not yet checked |
| **E3 Walk Squeeze Bound** | No walk component has a length exceeding `_MAX_WALK_SIZE` | Invariant | not yet checked |
| **E4 Plan Non-empty** | A Path of two or more nodes yields at least one component besides the `END_OF_MOVEMENT` sentinel | Invariant | not yet checked |
| **E5 Sentinel Terminus** | A Movement Plan ends with exactly one `END_OF_MOVEMENT` and contains no other | Invariant | not yet checked |

**There is no offline oracle for "sensible route".** Whether pathfinding picked a
*good* Path is a question only a running client answers, so the group stops at
structural properties — the ones that break silently and that a human reading a
failed golden cannot reconstruct.

**Reachability is corpus data, not a runtime query.** Each sampled pair is frozen
with the reachability the grid reported when the sample was generated, so a pair
that stops being reachable fails E1 instead of being skipped.

**Movement type coverage is capped by the compiler, not the corpus.**
`path_into_movements` can emit 13 of the 16 `MovementTypes`;
`FLASH_JUMP_LEFT`, `FLASH_JUMP_RIGHT` and `CROUCH` have no `ConnectionTypes`
counterpart (theirs are commented out as `NotImplemented`) and their builders
raise. The coverage matrix records those three as unreachable-by-construction
rather than as gaps in the corpus.

## Deliberately excluded

- **"No keyup without a preceding keydown" as accepted behaviour.** Initially
  excluded, because `_clear_opposites(strict=True)` emitted exactly that on
  purpose. Reversed: it is now **A6**, an Invariant, on humanization grounds, and
  the `strict` branch it was excluded for no longer exists.
- **Movement Plan correctness** — whether pathfinding chose a sensible route, or
  whether a node transition is legal. Real, but a question about
  `path_into_movements`, not about Input Sequences; it belonged to the test corpus
  ticket [#10](https://github.com/FlawlessNa/Legends/issues/10). **Partly
  reversed**: #10 brought the decidable half back as the **E** group above. Only
  "sensible route" stays excluded, for want of an offline oracle.

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
