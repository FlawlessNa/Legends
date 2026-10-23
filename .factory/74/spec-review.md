---
ticket: 74
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "_smart_rotation_target's centre computation and get_closest_mob_direction's agree on the same synthetic rectangles, tested by feeding both the same list"
---

# Spec review: one rectangle format for on-screen mobs

**Verdict: `changes-requested`.** I reviewed `spec.md` at `7f29ed6`. The core
of the spec is right:

- the model path already returns `x1, y1, x2, y2`;
- the contour path is the one producer that converts;
- `get_closest_mob_direction` is the one consumer that changes;
- the red test is real.

Three things block it.

- **Criterion 7 deletes a TODO that is still true.** It sits on the
  *character* box, which the intent wrongly says is already `x1, y1, x2, y2`
  (finding 1).
- **The spec misses an existing test file.** Its fixtures are written in
  `x, y, w, h`, and three of its tests go red under the new format (finding 2).
- **Two criteria are not decidable as written.** One is criterion 4, quoted
  above (finding 3). The other is criterion 1's "return annotation" (finding 4).

The rest are notes the plan can settle.

## 1. Criterion 7: the TODO is about the character box, and that box is still mixed-format

> the TODO about x1, y1, x2, y2 versus x, y, w, h in mobs_hitting.py is removed, and the comment it carried states the single format

**Evidence.** The TODO at `maple/decision_makers/mobs_hitting.py:160` sits in
`_mask_for_skill_range(self, pos)`. There, `pos` is the **character's**
on-screen position (`current_on_screen_position`), not a mob rectangle. The TODO
reads: "Detection model returns x1, y1, x2, y2, while detection configs returns
x, y, w, h". "Detection configs" means the character's `detection_configs`
section (`Character._set_detection_configs`).

That complaint still holds today. `Character.get_onscreen_position`
(`maple/model/characters/character.py:147-156`) has three branches:

- **model and configs:** `_cross_validate_results` returns
  `min(mx1, dx1), ..., max(mx2, dx2), ...`, which is `x1, y1, x2, y2`.
- **model only:** `extract_results` returns `x1, y1, x2, y2`.
- **configs only:** `res = detection_res`, the raw output of
  `_run_detection_methods`, which builds every candidate from
  `cv2.boundingRect` and filters on `rect[2]`/`rect[3]` as width and height.
  That is **`x, y, w, h`**, and it is returned unconverted (`x, y, w, h = res;
  return int(x), int(y), int(w), int(h)`). `_cross_validate_results` treats the
  same value as `dx1, dy1, dw, dh`.

The configs-only branch is reachable:

- `maple/launchers/launcher_leeching_v2.py` passes `detection_configs`;
- `Character` falls to that branch whenever no Character model is registered.

The issue's claim, "The character's own box is not affected", is therefore
wrong. So is the intent's premise that `Character.get_onscreen_position`
"already use[s]" `x1, y1, x2, y2`. If the Builder satisfies criterion 7 as
written, they delete the only marker of a live bug and replace it with a
comment that is false on one branch. Three readers consume this box as
`x1, y1, x2, y2`, and all three are affected:

- `_mask_for_skill_range`;
- `box_center`, which feeds `get_closest_mob_direction`;
- `_smart_rotation_target` (`x1, y1, x2, y2 = on_screen_pos`).

**Fix.** Pick one option and record it under "Decisions I made":

- **(a) Conservative, recommended.** Rewrite criterion 7 so the TODO stays,
  narrowed to name `Character.get_onscreen_position`'s configs-only branch as
  the remaining `x, y, w, h` source. File a follow-up issue for the character
  box. Add a line to the Shape saying the intent's premise about the character
  box holds only when a Character model is registered.
- **(b) Widen the scope.** Convert `detection_res` to `x1, y1, x2, y2` on the
  configs-only branch, with its own red test (a stubbed `_run_detection_methods`
  is enough), and add `character.py` to the intent's affected list. Do **not**
  decide in passing whether that branch should also apply `_detection_offset`,
  as the cross-validation branch does. That offset is a config value read off a
  client, and settling it is an Expectation.

Either way, the PR body must say that the intent's premise was corrected.

## 2. Existing tests encode `x, y, w, h`, and three of them go red

**Evidence.** `tests/test_maple/test_mobs_hitting_direction.py:26-30` defines
its mob fixtures "in the x, y, w, h shape `get_onscreen_mobs` returns", for
example `MOB_NEAR_RIGHT = (130, 40, 20, 30)`. I reran its four direction cases
under the spec's formula, `((x1 + x2) / 2, (y1 + y2) / 2)`, with the character
at `(100, 55)`. `MOB_NEAR_RIGHT` gets a centre of `x = 75`, which is left of the
character. Three tests then fail:

- `test_direction_points_at_the_closest_mob[mobs1-right]`;
- `test_direction_points_at_the_closest_mob[mobs2-right]`;
- the first assertion of
  `test_unidirectional_branch_derives_a_facing_from_the_on_screen_box`.

The spec's "Affected" list says "New unit tests" and names no changed tests.

**Fix.** Add a "Changed tests" section. It names this file, the four fixture
constants, the comment on line 26, and the behaviour that moved: the input
format of `get_closest_mob_direction`. Converting the fixtures to
`x1, y1, x2, y2` keeps every test's verdict. This file is also the natural home
for criteria 3 and 5, because `_FakeMobsHitting` already stubs the detection
call.

## 3. Criterion 4 is not decidable as written (the weakest criterion)

> _smart_rotation_target's centre computation and get_closest_mob_direction's agree on the same synthetic rectangles, tested by feeding both the same list

**Evidence.** `_smart_rotation_target` has no centre computation that a test
can feed. Its centres are an inline list comprehension (`_rotation_mixins.py:229`)
deep inside a method that returns a **minimap target**, after these steps:

- a threshold check against `next_target`;
- two `TIME_ON_TARGET` timing gates on `time.perf_counter()`;
- `update_attribute("current_client_img")`;
- `get_last_known_value("current_on_screen_position")`;
- a `mob_threshold` / `MIN_MOBS_THRESHOLD` count gate;
- a **majority vote** between left and right.

`get_closest_mob_direction`, by contrast, returns the side of the **nearest**
centre. The two answer different questions, so "agree" has no single reading.
It could mean the same centres, the same side, or the same side only when the
majority and the nearest coincide. The Shape also says `_smart_rotation_target`
is "unchanged", which leaves no shared code to test.

**Fix.** Make agreement structural, then pin the behaviour:

- **Shared helper.** Both consumers compute mob centres through one helper.
  `MobsHittingMixin.box_center` already exists and is already documented as
  `x1, y1, x2, y2`. Every `_smart_rotation_target` owner has `MobsHittingMixin`
  (asserted at `_rotation_mixins.py:184`). Rewrite the criterion as
  "`get_closest_mob_direction` and `_smart_rotation_target` both derive each
  mob's centre from `box_center`". Moving `_rotation_mixins.py:229` onto the
  helper is a refactor, and the existing suite must pass untouched.
- **Behavioural pin.** Name the observable: for a list of `x1, y1, x2, y2`
  rectangles, all left of the character's centre, whose `x, y, w, h` misreading
  would put the majority right, `_smart_rotation_target` returns a target whose
  x is less than `current_minimap_position[0]`. `_RotationOwner` in
  `tests/test_maple/test_rotation_target_handoff.py` is the scaffold to extend.
  The plan must list what the fake has to supply:
  - `_first_time_on_target = False` and an old `_last_target_reached_at`;
  - `current_client_img` and `current_on_screen_position`;
  - `mob_threshold`;
  - `current_minimap.map_area_width` and `current_map.vr_width`;
  - a feature with `left`, `right`, `top`, `avoid_edges` and `edge_threshold`.

  This test is green before and after, so it is a pin, not the red test. The
  spec already says so.

## 4. Criterion 1: "return annotation say so" has no checkable meaning

> get_onscreen_mobs returns x1, y1, x2, y2 on both paths, and its docstring and return annotation say so

**Evidence.** Today the annotation is `tuple[Sequence[int], ...]`. No
annotation can "say" a coordinate order unless the spec names one. Two honest
readers could disagree about whether a given annotation meets the criterion.
There is also a knock-on: `extract_results` (`botting/visuals/in_game_visuals.py:399`)
is annotated `tuple[Sequence[int], ...]` and shared with `Character`. A narrower
return type on `get_onscreen_mobs` therefore needs one of two things:

- `extract_results` narrowed too, which puts `in_game_visuals.py` in the radius
  and surfaces its Pyright violations;
- a conversion on the model path.

**Fix.** Name the annotation exactly, for example
`tuple[tuple[int, int, int, int], ...]`, or a named alias whose docstring says
`x1, y1, x2, y2`. Name the docstring's `:return:` text exactly. Then let the
plan decide where the narrowing happens.

## 5. Criterion 2's contour-path test is buildable, with two conditions the spec should state

**Evidence.** I built it in a scratch script against today's code. It returned
`((10, 20, 30, 40),)`, so the criterion's red claim holds. The script used:

- a concrete `BaseMob` subclass defining `_filter` (return the contours) and
  `_preprocess_img` (a 100x100 `uint8` image with `img[20:60, 10:40] = 255`);
- any int as `handle`.

`detection_model` stays `None`, because no test registers a model in
`InGameDetectionVisuals._models`.

Two conditions:

- **`debug=False` is required.** `base_mob.py` has a module constant
  `DEBUG = True`, and `debug` defaults to `True`. With either left on, the
  contour path calls `_debug`, which draws on the image and then calls
  `cv2.imshow` and `cv2.waitKey(1)`. "No client" does not rule out opening a
  GUI window from the suite.
- **The contour path is unreachable in production.** Every live mob is built by
  `MapleMob.create`, which sets `_filter` and `_preprocess_img` to `None`. So a
  mob without a model raises `TypeError` at `self._preprocess_img(image)`, before
  the `try` block. Criterion 2 fixes a contract, not a live path. The Shape
  should say so, so that nobody reports it as a live fix.

**Fix.** Add "called with `debug=False`" to criterion 2, and add a sentence to
the Shape. Leave the `TypeError` out of scope.

## 6. Criterion 6's grep is well formed but checks one spelling

> grep -rn "rect\[0\] + rect\[2\] /" maple/decision_makers finds nothing, ...

**Evidence.** The pattern is valid basic regex: `\[` is a literal bracket and
`+` is a literal plus. Run today, it matches exactly one line,
`_mob_mixins.py:80`. It does not match `_rotation_mixins.py:229`, because a `)`
comes before the `/`. So the grep does separate the two conventions. Two gaps:

- It ignores the y half of the same bug, `rect[1] + rect[3] / 2`.
- It is scoped to `maple/decision_makers`, where the issue's grep covers
  `maple/`.

**Fix (optional).** Use
`grep -rnE "rect\[[01]\] \+ rect\[[23]\] /" maple/`, with
`maple/model/interface/dynamic_components/inventory.py:106` as the only
permitted hit. That hit is a correct read of the inventory code's own
`boundingRect`. Listing the allowed hit is the pattern `.factory/217` used.

## 7. Criterion 5 names an unobservable value

> for a mob at x1=400, x2=440 the computed centre x is 420, where today's get_closest_mob_direction gives 620

**Evidence.** "The computed centre" is a local inside `get_closest_mob_direction`.
The Verification section already gives the observable version: the character
between 420 and 620.

**Fix.** Phrase it as the test sees it: "`get_closest_mob_direction((500, 5),
[(400, 0, 440, 10)])` returns `"left"`; today it returns `"right"`". If
finding 3 is taken, assert `box_center((400, 0, 440, 10)) == (420.0, 5.0)` as
well.

## 8. Things I checked that need no change

- **`get_mob_count`** is unaffected. It reads only `len(...)`.
  `ensure_mob_still_spawn.py:49,133` and `mob_count_in_img` count, not read
  coordinates.
- **No missed consumer.** The only readers of mob rectangles are
  `get_closest_mob_direction` and `_smart_rotation_target`, both through
  `get_mobs_positions_in_img`. I grepped the whole repo, including `toolkit/`,
  `ml_training/`, `scripts/` and `tests/`, for `get_onscreen_mobs`,
  `get_mob_count`, `get_mobs_positions_in_img`, `get_closest_mob_direction`,
  `mobs_locations` and `rect[` indexing. Nothing else reads them.
- **YOLO's key order.** In the pinned `ultralytics==8.4.135`, `Results.summary`
  builds `box` by inserting `x1, y1` and then `x2, y2`, so
  `tuple(dct["box"].values())` is `x1, y1, x2, y2`. The model path needs no
  change.
- **`mask` in `extract_results`** unpacks `x1, y1, x2, y2` and slices
  `intersection[y1:y2, x1:x2]`. That is consistent with the model path's
  format. The contour path ignores `mask` entirely. That gap predates this
  ticket and is not a format bug. Add it to "Not in scope", so that the Builder
  does not fold a mask fix in.
- **The "not without asking" list.** Nothing in `botting/controller/` changes,
  and criterion 8 checks that mechanically. Nothing touches an ADR, the
  telemetry envelope, map JSON, pinned versions or `inventory_manager.py`.
  `COMBAT_MOBS_HIT` keeps its schema; only the value of `direction` changes,
  which the spec's "Could not verify" section already names.

## What this review could not verify

- I did not run pytest. The three red tests in finding 2 are computed from the
  fixtures, not observed.
- I did not check whether any current launcher actually runs with a Character
  model absent. I confirmed only that the configs-only branch of finding 1 is
  reachable and that `launcher_leeching_v2.py` passes `detection_configs`.
