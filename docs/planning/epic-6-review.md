# Review: epic #6 against the virtual-position rewrite (#422)

Written 2026-11-09 on `epic/mscw-screen-reading` at `ef9c959`. This is a
**proposal**. No issue was closed, edited or re-parented. The maintainer
approves, and the orchestrator applies the changes.

## In one minute

Epic #6 ("Movement testing, tuning and calibration framework") was built on the
old movement system: minimap pixels, `MinimapGrid`, and one JSON file per map.
Its Layer A (the defects plus an offline movement lab) is almost all done and
closed. Layer B (calibration) built its tools: the Trial framework (#116) and the
Stuck detectors (#128). Layer C (Attempt tracking) was never started. Epic #302
Part 2 now rebuilds the ground under all three: virtual px, `WorldMap`,
`FootholdGraph` (#395), `VRPhysics` with Calibration constants (#394), then
Movement Plans (#396), Trials (#397) and decision makers (#398) in virtual px.

**Recommendation: close #6, and move what is still valid.**

- Two tickets are real work that #302 needs and has not planned. Both move into
  #302:
  - **#114**: the seam-jump defect. It is still live on the new graph, measured
    below.
  - **#12**: Attempt detection. #396, #397 and #400 all report Attempts, but
    nothing counts them.
- **#111** and **#133** become acceptance lines on #396.
- **#117** becomes acceptance lines on #393.
- **#14**, **#118** and **#15** are superseded by #394, #397 and #400.
- **#108** and **#120** are still valid but are not #302's work. They become
  standalone tickets.
- #302's critical path gets **one new blocker before #396**. It is #114
  re-scoped, and it is small and can start now. The rest runs in parallel.

## What #6 was, for someone who hasn't read it in months

- **Destination:** a movement system whose known defects are fixed and whose
  behaviour is pinned by an offline lab, reached in three layers:
  - (A) fixes plus a green lab;
  - (B) calibration tooling and fitted constants;
  - (C) Attempt analysis from telemetry.
- **Done when:**
  - the lab is green against fixed code;
  - Calibration constants are fitted and used by compilation;
  - no design decision is left open.
- **Built and closed:**
  - the Held-Keys Ledger and compilation at dispatch (#24, #29, #30, ADR 0002);
  - the invariant catalogue (#9) and the lab: Corpus, Goldens, Provenance
    (#10, #101 to #104);
  - about 15 compile defects (#25 to #28, #75, #84, #97 to #100, #109, #110,
    #113, #131, #132);
  - the calibration method (#13: Trial, Calibration constant, Knob, and
    rate vs feasibility);
  - the Trial framework (#116);
  - precision movements and Attempt budgets (#11, #129);
  - Stuck detection (#119, #128).
- **Still open:** #12, #14, #15, #108, #111, #114, #117, #118, #120, #133.

## Decisions, ticket by ticket

| Ticket | Decision | Why | Evidence | Proposed action |
| --- | --- | --- | --- | --- |
| **#12** Attempt detection from telemetry | **Still valid, re-scoped. Moves to #302.** | #302 counts Attempts in three places and never says how. The blocker it waited on (the logging map's telemetry format) is gone: #16 is closed, ADR 0001 is in force, and `movement.*` Event Types exist. | #397's acceptance list has "The **existing** Attempt analyzer reports precision movements in virtual px". No analyzer exists: `grep -rn Attempt maple toolkit` finds only `_map_mixins.py` and `action_data.py`, neither an analyzer. #400 reports "every Precision movement row with its Attempts against its Attempt budget". #396's live check reports them too. `PlanStartedPayload` (`maple/telemetry_events.py:230`) has no precision flags, so an analyzer can't yet tell which component was a precision movement. | Re-parent to #302 as **T32**, re-worded in virtual px (below). It needs #396 first, and #400 needs it. Remove the analyzer line from #397. |
| **#14** Calibration constants config | **Superseded** by #394, with the rest moved to #396. | #394 decided where the constants live and how compilation gets them: a `calibration` mapping (walk, jump, climb, teleport) from the profile into the bot's kwargs, applied as multipliers on top of the speed and jump multipliers. `grid.speed` is replaced by `VRPhysics.walk_speed` in #396. The constants #14 listed that are still hard-coded are compile constants, not physics, and #396 has to convert or name them. | `maple/model/mechanics/physics.py:44-63` (`Calibration`, `CALIBRATION_KEYS`); `maple/bots/maple_bot.py:71,91,211`; `profiles/example.yaml:106`. Still hard-coded: `FIRST_DELAY = 0.5` (`maple/actions/movements_v2.py:17`); the 0.75 s jump hold (`movements_v2.py:197,220,224,281`); `_FALL_LEN_EXT = 3` and `_MAX_WALK_SIZE = 5`, both in minimap px (`movement_mechanics_v2.py:405-406`); `_NARROW_PLATFORM_THRESHOLD = 5` (`:68`). | Close as superseded by #394. Add the conversion line to #396 (edit 396-B). |
| **#15** Verify green, re-enable the bot, close the map | **Superseded.** | Each of its four done-lines now has an owner in #302. | Fix tickets: this table. Lab green across the Corpus: #396 ("The movement Invariants pass on the rebuilt Corpus"). Constants fitted and used: #397 (`physics.json` → Calibration constants) and #394 (used). Bot run and watched: #400 (Ellinia bottom to top). | Close with #6, pointing at #400. |
| **#108** `cast_skill` double cast; re-measure `animation_time` | **Still valid as written. Not #302's.** | It is about skill timing, not navigation. Virtual px doesn't touch it. The `# TODO - Confirm` values are still there. | `maple/model/characters/magicians.py:86,104,111`. | Re-parent out of #6 as a standalone `ready-for-human` ticket. Optionally, watch for it in #398's live check with monsters (edit 398-B). |
| **#111** `jump_on_rope` called with `'up'`/`'down'` | **Still valid, re-scoped into #396.** | The new graph makes the case first-class: a straight-up jump that grabs a rope's bottom is a graph move. The `'down'` half goes away, because the graph has no drop onto a rope (`DROP` and `FALL` land on platforms). | `foothold_graph.py:526-535` (`JUMP`, `Direction.UP`, target a rope); `_drop` at `:355` lands on platforms only. The call still passes `direction` under `# pyright: ignore[reportArgumentType]` (`movement_mechanics_v2.py:246-259`). #131 already stopped the double release, so what is left is the compiled shape plus a live check. | Re-parent to #302. #396's PR closes it (edit 396-A). #400 reports whether the rope grabs landed (edit 400-B). |
| **#114** Jump connections across touching co-planar features | **Still valid, re-scoped. Moves to #302 before #396.** | The defect survives the rewrite in a new form. Costs are now seconds, not edge counts, so a jump over a join costs exactly what the walk costs. A* breaks the tie toward the jump. | Measured offline, with no client. On #114's own geometry, as two joined platforms, `FootholdGraph` plans `walk → JUMP right → walk` at 1.782 s, the same as walking. On real **Ellinia**: 26 join walks, 46 jump ranges between joined platforms, and **11 of 22** 120-px trips centred on a join plan a jump. All 11 cost exactly the walk's time (0.960 s), and every join is flat (rise 0). Damp Forest has no joins. The existing test `test_a_platform_ending_on_another_walks_across_and_does_not_fall` (`tests/test_maple/test_foothold_graph.py:328`) checks the duration only, so it passes either way. | Re-parent to #302 as **T31**, re-worded (below). It blocks #396 so the Goldens are recorded once. |
| **#117** Characterise the minimap-detection instrument | **Superseded by #393, with additions.** | The instrument is now the fused position: play area plus minimap. #393 is the tool that measures it, but it reports `UNSURE` and fallback rates, not stationary jitter or latency. Those are what the Stuck thresholds and Trial repetition counts were meant to come from. | `maple/movement_recovery.py:93-94` (`jitter_bound = 1.0`, "The floor is #117's stationary-jitter figure"). #393's acceptance list has no jitter or latency line. | Close as superseded by #393. Add 393-A. |
| **#118** Feasibility probes with binary sweeps | **Superseded by #397, with additions.** | #397's `physics.json` measures jump arc and teleport reach. The new graph has three feasibility constants marked unverified, and #397 names only one of them. #13's rule that feasibility errors are rounded toward safe has to move with it. The venue is Ellinia, not the #106 playground map, which goes with `configs/maps/` in #399. The vehicle becomes a maintainer-started Trial session, not a key-sending toolkit script. | `foothold_graph.py:61-64` (`DROP_REACH`, "unverified (#397)") and `:88-92` (`ROPE_JUMP_SPEED`, the same). `physics.py:31-33` (`TELEPORT_REACH`, one value for every direction). The old grid split teleport up and down (`physics.py:275-276`, `# TODO FIGURE THIS OUT`). | Close as superseded by #397. Add 397-B. |
| **#120** First convergence Trials and Knob sweeps | **Still valid, re-scoped. Not #302's.** | #302 defers Knob sweeps on purpose. Fitting the Stuck thresholds is also #120's work, and it needs a working system first. | #302 § Part 2 › Decisions (C1): "Left for later: Knob sweeps". #397's Constraints: "Knob sweeps for new controller defaults are out of scope". `movement_recovery.py:31-32,88`: "#120's Trials fit the values". | Re-parent out of #6 as a standalone `ready-for-human` ticket, blocked by #400 and #393. Re-word it to virtual px, game map names, and #393's figures in place of #117's. Drop the #106 blocker. |
| **#133** Lab tests order-sensitive through the shared `random_delay` | **Still valid, re-scoped into #396.** | It is smaller than when it was filed: B1 and B2 moved behind the `lab` marker (#172, 2026-10-15), so it no longer turns the default suite red. But #396 rebuilds the Corpus and the invariant run, which is the cheap moment to seed each record. The Goldens already do this. | `tests/test_maple/movement_lab/test_invariants.py:385,425` (`@pytest.mark.lab`); `test_goldens.py:167-170` (`_seeded_compile`, `random.seed(SEED)`). | Re-parent to #302. #396's PR closes it (edit 396-D). |

## Epic #6 itself: close it

**Why close rather than keep or fuse.**

- **Keeping #6 open** would leave two epics planning the same Movement Plans,
  Trials and Calibration constants in different units. Nothing left in it is
  independent of #302 except #108 and #120. Neither is movement-framework work
  that needs an epic.
- **Fusing all of #6 into #302** would bring Layer C, Knob sweeps and Stuck
  threshold fitting into an epic whose done-line is "Ellinia bottom to top"
  (#400). #302 already chose to leave Knob sweeps for later (C1).
- **Closing it with the value moved** keeps #302's scope as agreed. It adds only
  the two pieces #302 depends on without knowing it (#114, #12).

**Where #6's destination goes.**

| #6 layer | Owner after this |
| --- | --- |
| A: fixes plus a green lab | T31 (#114); #396 (Corpus rebuilt on `WorldMap`, Invariants pass, Goldens re-recorded, plus #111 and #133) |
| B: calibration tooling and fitted constants | #393 (the instrument, plus #117's figures); #394 (constants consumed); #397 (Trials in virtual px, physics schedule, plus #118's feasibility constants) |
| C: Attempt analysis | T32 (#12) |
| Done-line "the bot has been run and observed moving correctly" | #400 |
| Knob sweeps and Stuck threshold fitting | #120, standalone, after #400 |

**What carries over from #6's "Not yet specified".** Put these in #302 Part 2 as
a short "Carried over from #6" note, so they aren't lost when #6 closes:

- **B1 does not hold.** `truncate` can cut a Movement Plan mid-jump. It has never
  had a fix ticket. #396 reports its rate on the rebuilt Corpus (396-E). A fix
  ticket follows only if the rate or #400 says it matters.
- **The Path refresh (0.1 s) against the decision-loop interval**: a Knob
  question, for #120.
- **Whether a Trial record carries the Delivered Prefix**, or reaches it by
  Correlation ID: T32 decides it, because it is the first reader.
- **When a Golden may be regenerated rather than investigated**: #396
  re-records them all. The policy is still open once fitted constants start
  moving timings.
- **`OVERHEAD` measured per process vs fitted**: still open. It only matters
  for the lab's determinism.

**Vocabulary.** Everything #6 put in `CONTEXT.md` carries over. Some entries
change with virtual px. #399 already rewrites `CONTEXT.md`, so the changes go
there (399-A):

| Term | Carries over? | What changes |
| --- | --- | --- |
| Trial, Trial schedule, Trial record | Yes, as is | Positions and tolerances in virtual px; the map named by game name (#397) |
| Calibration constant | Yes, re-worded | "never an absolute **minimap** distance, so it ports to every map's **scale**" loses its reason: virtual px is one scale on every map. Keep "a multiplier on the derivation, never an absolute distance". "Per stat-value as session config" becomes the profile's `calibration:` mapping on top of the speed and jump multipliers (#394). |
| Knob | Yes | The narrow-platform and edge-departure thresholds are in virtual px |
| Precision movement, Attempt, Attempt budget | Yes | The taxonomy's plan signatures name grid `MovementTypes`; restate them on graph moves (#396) |
| Movement lab, Golden, Provenance | Yes, as is | — |
| Fixture map, Corpus | Yes, re-worded | A Fixture map becomes synthetic `MapData`, not a hand-written map config; the Corpus's maps become `WorldMap`s (#396) |
| Stuck and its symptoms | Yes | Stagnation is "remaining Path length in nodes". Nodes go, so it becomes the graph Path's remaining time or length (398-A) |

## Ordering for #396 to #400

```
#395 (merged) ──► T31 (#114: no free jump across a join) ──┐
#392 ─────────────────────────────────────────────────────┴──► #396 ──┬──► #397 ──┐
                                                                       ├──► #398 ──┴──► #399 ──┐
                                                                       └──► T32 (#12: Attempts) ─┴──► #400
#393 (plus #117's figures) ── feeds ──► #398's provisional thresholds, and #120 later
```

- **T31 can start now.** It needs only #395, which is merged. It blocks #396 so
  the Goldens and the Corpus are recorded on the final graph once.
- **T32 runs beside #397, #398 and #399.** Only #400 waits for it, so the
  critical path doesn't get longer.
- **No ticket is renumbered.** T31 and T32 are the next free numbers. The #302
  checklist lists them in order, with T31 above #396 and T32 above #400.

## Proposed tracker actions

**Close:**

- **#14**, as superseded by #394 (and 396-B);
- **#15**, as superseded by #400;
- **#117**, as superseded by #393 (and 393-A);
- **#118**, as superseded by #397 (and 397-B);
- **#6**, after the moves below, with a closing comment that points here.

**Re-parent into #302:**

- **#114** as T31 and **#12** as T32, both re-worded below;
- **#111** and **#133**, closed by #396's PR.

**Re-parent out of #6, standalone:**

- **#108**, unchanged;
- **#120**, re-worded: virtual px, game map names, #393's figures, blocked by
  #400 and #393, the #106 blocker dropped.

### New wording for #114 (T31)

> **T31 · No planned jump across a join that walking matches** (from #114).
> Part of #302 · Blocked by none · Blocks #396.
>
> **Goal.** Where two platforms join (a `WALK` across a join), `FootholdGraph`
> also stores `JUMP` ranges from one to the other. On flat ground the jump costs
> exactly the walk's time, and A* picks it: on Ellinia, 11 of 22 120-px trips
> centred on a join plan a jump that saves 0 s. This is #114's defect, now on
> the graph.
>
> **Acceptance.**
> - A path never takes a `JUMP` where walks along the same platforms reach the
>   same landing in no more time: ties go to the walk. The jump ranges stay in
>   `moves`; only the choice changes.
> - The join test (`test_foothold_graph.py:328`) also asserts the moves: walks
>   only.
> - `client_files`: on Ellinia and Damp Forest, no path between two points on
>   joined platforms holds a jump that saves no time.
>
> **Constraints.** No consumer yet, so no keys change (C-KEYS).
>
> **Can't be verified offline.** Whether a jump across a flat join was ever
> harmful in the game. Choosing the walk is the conservative choice.

### New wording for #12 (T32)

> **T32 · Attempts from telemetry: how they're counted, and the analyzer**
> (from #12). Part of #302 · Blocked by #396 · Blocks #400.
>
> **Goal.** #396's live check, #397 and #400 report each Precision movement's
> Attempts against its Attempt budget. This ticket defines how Attempts are
> counted, and builds the analyzer that counts them.
>
> **Acceptance.**
> - Delimitation is "next gesture at the same transition", never "next cycle"
>   (`CONTEXT.md` § Movement attempts, #11). Success is detected per taxonomy row
>   (PM1 to PM5) from the virtual position.
> - `movement.plan_started` gains, additively, each component's precision flags
>   (`narrow`, `edge_departure`) and the transition's virtual take-off and
>   landing.
> - An offline analyzer reads a Session's `telemetry.jsonl` (and Trial records,
>   joined by Correlation ID). Per instance it reports the row, the Attempts,
>   the outcome (*fell* separately for PM3), and the budget verdict.
> - It decides whether a Trial record should carry the Delivered Prefix (#6's
>   open question).
> - Unit tests on synthetic telemetry streams.
>
> **Can't be verified offline.** That the rows it finds match what a person
> watching the Session would count: the first check is #400's Session.

### Exact edits to #302's tickets

**#396 (T26).** Add to Acceptance:

- **396-A** (#111): `- [ ] FootholdGraph's straight-up JUMP that grabs a rope
  compiles to its own typed shape: nothing passes 'up' to jump_on_rope's
  Literal["left", "right"], and the pyright ignore at movement_mechanics_v2.py:259
  is gone. The graph has no drop onto a rope, so the JUMP_DOWN → CLIMB_UP case
  is removed. Closes #111's offline half.`
- **396-B** (#14): `- [ ] Every constant in minimap px or grid units is
  converted or retired, each named in the PR with its conversion:
  _FALL_LEN_EXT (3), _MAX_WALK_SIZE (5), _NARROW_PLATFORM_THRESHOLD and
  _EDGE_DEPARTURE_THRESHOLD (5). The 0.75 s jump hold in single_jump and
  jump_on_rope either comes from VRPhysics' jump duration or stays a named
  constant marked "until measured by #397".`
- **396-C**: `- [ ] The invariant catalogue restates E1 to E3 for graph Paths
  (they name grid nodes, grid neighbours and _MAX_WALK_SIZE), and B3's "needs
  #13/#14" points at #397. The precision-movement taxonomy's plan signatures
  name graph moves.`
- **396-D** (#133): `- [ ] The lab compiles each Corpus record from its own
  seed, as test_goldens._seeded_compile already does, so no pass or fail depends
  on test order. Test-only: random_delay in production is unchanged. Closes
  #133.`
- **396-E**: `- [ ] The PR reports the lab measurements B1 and B2 on the rebuilt
  Corpus (pytest -m lab tests/test_maple/movement_lab).`
- **396-F**: Blocked by: add T31. Under "Can't be verified offline", change
  "every Precision movement row seen with its Attempts" to "…with its Attempts,
  counted by hand (the analyzer is T32)".
- **396-G** (a note under Constraints): `The thresholds' unit changes under the
  Trial Knobs: configs/trials Knob values are 16× off until #397 converts them.
  Trials can't run in between anyway, since they judge in minimap px. Say so in
  the PR.`

**#397 (T27).**

- **397-A**: remove `- [ ] The Attempt analyzer reports precision movements in
  virtual px.` (It moves to T32.)
- **397-B** (#118): replace the `physics.json` line with: `- [ ]
  configs/trials/physics.json on Ellinia measures walk speed (long walks), climb
  speed (a rope and a ladder), jump arc (jumps between known platforms), teleport
  reach sideways, up and down, the drop reach (DROP_REACH) and whether a jump
  off a rope rises (ROPE_JUMP_SPEED). An analyzer step turns its records into
  Calibration constants. Feasibility values (jump height and reach, teleport
  reach, drop reach) are rounded toward conservative: an optimistic one becomes
  a stuck-loop (#13, rate vs feasibility).`
- **397-C**: under "Where to look", add `#13's resolution in #6 (rate vs
  feasibility) and #118`.

**#398 (T28).**

- **398-A**: add `- [ ] StuckThresholds (maple/movement_recovery.py) move to
  virtual units: jitter_bound (1.0 minimap px) and the Plan Churn quantization
  cell in virtual px, with the conversion in the PR. progress_epsilon counts
  Path nodes, which no longer exist: Stagnation is restated on the graph Path's
  remaining time or length. The values stay provisional; #393's stationary
  jitter is their floor, and #120 fits them.` Today the ticket names only
  `_recovery_mixins.py`, which holds the plumbing; the thresholds are in
  `movement_recovery.py:88-110`.
- **398-B** (optional, #108): under "Can't be verified offline", add `On the
  map with monsters, note any double cast (#108).`

**#393 (T23).**

- **393-A** (#117): add `- [ ] With the character standing still, it reports
  each read's spread (minimap, play area, fused) in virtual px; per frame, it
  records the frame's age when the fused reading is made (captured_at to read).
  These are the instrument figures the Stuck thresholds and Trial repetition
  counts derive from (#117).` Under "Can't be verified offline", add `a 60 s
  stationary sample on Ellinia, and the maintainer holding a walk`.

**#399 (T29).**

- **399-A**: add to the `CONTEXT.md` line: `…and amends, from #6's vocabulary:
  Calibration constant (no "minimap distance" or "map's scale"; the profile's
  calibration: mapping), Knob (virtual px), Fixture map and Corpus (synthetic
  MapData and WorldMaps), Stagnation (no Path nodes).`

**#400 (T30).**

- **400-A**: Blocked by: add T32.
- **400-B**: under Acceptance, `The PR also says whether every straight-up rope
  grab landed on the rope (#111) and whether any path jumped across a flat join
  (#114).`

**#302's checklist (Part 2 › Tickets).** Add `- [ ] #114 T31 · No planned jump
across a join that walking matches (before #396)` above #396. Add `- [ ] #12 T32
· Attempts from telemetry: how they're counted, and the analyzer` above #400.
Add a "Carried over from #6" note with the five items above.

## What I could not verify

- **Whether any of this matters in the game.** Each item below rests on how the
  real client behaves:
  - whether a jump across a flat join is harmful or only a cosmetic oddity
    (T31 picks the walk as the safe default);
  - whether the straight-up rope grab's compiled shape lands on the rope (#111);
  - jump arc, teleport reach per direction, drop reach, and whether a jump off a
    rope rises (#118 → #397);
  - every `animation_time` (#108);
  - jitter and latency (#117 → #393).
- **The seam figures.** They come from `FootholdGraph` on the extraction in
  `Legends-worktrees/t390/data/game_data`. I didn't check that extraction's
  `status`. I sampled only 120-px trips centred on each join, on Ellinia and
  Damp Forest. A different sample would give different counts, not a different
  conclusion: every jump found was an exact tie.
- **No code ran beyond that measurement and reading.** No `pytest` run (this
  change is one Markdown file), no `client_files` or `frames` tests, no live
  game, no probe.
- **No keys change** from this ticket. The proposed edits to #396, #397, #398
  and #400 change which keys reach the game when those tickets are worked, as
  they already say.
