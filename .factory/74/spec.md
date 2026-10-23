---
ticket: 74
stage: design
method: suite
criteria:
  - get_onscreen_mobs returns x1, y1, x2, y2 on both paths, its docstring says so, and its return annotation is tuple[tuple[int, int, int, int], ...]
  - on the path without a model, a test subclass of BaseMob whose filtered contour has bounding rect x=10, y=20, w=30, h=40 yields (10, 20, 40, 60) when called with debug=False, with no client and no detection model
  - get_closest_mob_direction computes each mob's centre with MobsHittingMixin.box_center, and get_closest_mob_direction((500, 5), [(400, 0, 440, 10)]) returns "left", where today it returns "right"
  - _smart_rotation_target computes its mob centres with MobsHittingMixin.box_center too, and a behaviour test built on the _RotationOwner fake, with x1, y1, x2, y2 mob rectangles left and right of the character, gets the target on the side the mobs are on
  - grep -rnE "rect\[[01]\] \+ rect\[[23]\] /" maple/ matches only maple/model/interface/dynamic_components/inventory.py, whose rectangles come from its own boundingRect and are out of scope
  - the TODO in mobs_hitting.py stays, narrowed to say what is still true, that a character configured from detection configs with no model returns x, y, w, h from Character.get_onscreen_position, and it names the follow-up issue #231 that fixes it
  - tests/test_maple/test_mobs_hitting_direction.py's four mob fixtures and the comment above them move to x1, y1, x2, y2, named in the plan as a changed test whose behaviour moved, and the file passes
  - no file under botting/controller/ changes, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
revised_after: spec-review.md (changes-requested, 7 findings)
accepted: maintainer approved the first version on 2026-10-23; this revision keeps its outcome and narrows the TODO change, see "What changed after approval"
---

# Spec: one rectangle format for on-screen mobs

## Source

Issue #74 (part of #46). The intent was accepted by the maintainer.

## Shape

- **`BaseMob.get_onscreen_mobs`.**
  - The path without a model converts each `cv2.boundingRect` to `(x, y, x + w, y + h)`.
  - The model path is unchanged, because `extract_results` already returns `x1, y1, x2, y2` (YOLO's box, ultralytics 8.4.135).
  - The docstring and the annotation `tuple[tuple[int, int, int, int], ...]` say so.
  - If narrowing the annotation makes pyright require `extract_results` (shared with `Character`, in `botting/visuals/in_game_visuals.py`) to narrow too, that is in scope. Its runtime behaviour does not change.
- **`get_closest_mob_direction`** takes centres from `MobsHittingMixin.box_center`, the existing helper that already reads `x1, y1, x2, y2`. Its docstring's "(x, y, w, h)" becomes "(x1, y1, x2, y2)".
- **`_smart_rotation_target`** takes its centre x from `box_center` too, so both consumers share one definition. Its behaviour on `x1, y1, x2, y2` input is unchanged, and the new test pins it.
- **The path without a model is a contract, not a live path.** No real mob takes it today: `MapleMob` sets `_filter` and `_preprocess_img` to `None`. The test fixes the contract, so a future mob that uses it cannot reintroduce the split.

## What changed after approval

The first version deleted the TODO in `mobs_hitting.py`. Spec review found it is **still true**, about the character's box rather than the mobs'. When a character is configured from detection configs with no model, `Character.get_onscreen_position` returns `x, y, w, h` unconverted (`maple/.../character.py`, the `res = detection_res` branch). `launcher_leeching_v2.py` uses that setup.

So the issue's claim that "the character's own box is not affected" is wrong for that branch. The TODO stays, narrowed to that branch. The fix is a follow-up ticket, because it touches the character's detection and a measured offset there, which is not this ticket's to change.

## Verification method: suite

**Red tests:**
- `get_closest_mob_direction((500, 5), [(400, 0, 440, 10)])` returns `"right"` today;
- the contour test returns `(10, 20, 30, 40)` today.

**The shared-centre test** is new. It guards against the two consumers drifting apart again.

**Changed tests:** `tests/test_maple/test_mobs_hitting_direction.py`. Its fixtures `MOB_FAR_LEFT`, `MOB_NEAR_LEFT`, `MOB_NEAR_RIGHT` and `MOB_FAR_RIGHT`, and the comment above them, change from `x, y, w, h` to `x1, y1, x2, y2`. That is the moved behaviour: the input format of `get_closest_mob_direction`. Three of its tests go red without the fixture change. The expected directions stay the same.

## Could not verify (for the PR)

**This changes which direction key reaches the game when a detection model is in use.** It is correct by construction, but nothing offline shows the character facing the right mob in a live session. Watching one `mobs_hitting` rotation on a map with a detection model would confirm it.

## Not in scope

- The inventory slot centre (`inventory.py:106`), which reads its own `boundingRect` correctly.
- The character's configs-only branch: the follow-up ticket.
- `extract_results`'s `mask` handling on the path without a model. That path ignores `mask` today, a pre-existing gap.
