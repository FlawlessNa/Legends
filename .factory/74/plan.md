---
ticket: 74
stage: build
radius:
  - botting/models_abstractions/base_mob.py
  - botting/visuals/in_game_visuals.py
  - maple/decision_makers/mixins/_mob_mixins.py
  - maple/decision_makers/mixins/_rotation_mixins.py
  - maple/decision_makers/mobs_hitting.py
  - tests/test_botting/test_base_mob_rects.py
  - tests/test_maple/test_mobs_hitting_direction.py
  - tests/test_maple/test_smart_rotation_centres.py
  - .factory/74/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_maple/test_mobs_hitting_direction.py::test_a_mob_left_of_the_character_in_x1y1x2y2_is_to_the_left
  red_output_sha: ab688f5d8b4a
  suite: pass
docs_cleared:
  - path: docs/**, CONTEXT.md, botting/AGENTS.md, maple/AGENTS.md, tests/AGENTS.md
    reason: grep for "x, y, w, h", get_onscreen_mobs and get_closest_mob_direction finds no mention outside the code and tests in the radius, so no coupled doc exists
---

# Plan: one rectangle format for on-screen mobs

## Radius

| Path | Why |
| --- | --- |
| `botting/models_abstractions/base_mob.py` | contour path returns `(x, y, x + w, y + h)`; docstring and annotation `tuple[tuple[int, int, int, int], ...]` |
| `botting/visuals/in_game_visuals.py` | `extract_results` narrows to the same annotation, built as an explicit four-element tuple. Runtime behaviour unchanged |
| `maple/decision_makers/mixins/_mob_mixins.py` | `get_closest_mob_direction` takes centres from `box_center`; docstring says `(x1, y1, x2, y2)` |
| `maple/decision_makers/mixins/_rotation_mixins.py` | `_smart_rotation_target` takes its centre x from `box_center` |
| `maple/decision_makers/mobs_hitting.py` | the TODO narrowed to the configs-only character branch, naming #231 |
| `tests/test_botting/test_base_mob_rects.py` | new: the contour-path contract |
| `tests/test_maple/test_mobs_hitting_direction.py` | red test, and the changed fixtures below |
| `tests/test_maple/test_smart_rotation_centres.py` | new: the shared-centre behaviour test |

## Order of work

1. Write the red tests; run them against the unchanged source; save the `E` lines.
2. `base_mob.py` and `in_game_visuals.py` together (the annotation forces both), then the two mixins, then the TODO.
3. Fixture change in `test_mobs_hitting_direction.py`.
4. Full suite, ruff, pyright on the changed files.

## Notes from the passing spec review

- **Note a, `in_game_visuals.py` is in the radius from the start.** Pyright rejects `tuple[Sequence[int], ...]` against the 4-tuple annotation, and `tuple(map(round, ...))` is `tuple[int, ...]`, so `extract_results` builds an explicit `(x1, y1, x2, y2)` from the box's four values.
- **Note b, criterion 4's test.** Expected: the target goes to the side with **more** mobs (a tie goes right, and the fixture has none). The majority side is **left**, with mobs that would flip right if misread as `x, y, w, h`. Character centred at x 100; `(70, 40, 90, 70)` has true centre 80 (left), misread 115 (right). Built on the `_RotationOwner` fake.
- **Note c, for the PR body.** The approved intent said the TODO in `mobs_hitting.py` would be resolved and that the character's box was already consistent. The spec corrected both: with detection configs and no model, `Character.get_onscreen_position` still returns `x, y, w, h`. The TODO stays, narrowed, and the fix is follow-up #231.

## Changed tests

| Test | Behaviour that moved |
| --- | --- |
| `tests/test_maple/test_mobs_hitting_direction.py`: fixtures `MOB_FAR_LEFT`, `MOB_NEAR_LEFT`, `MOB_NEAR_RIGHT`, `MOB_FAR_RIGHT` and the comment above them | input format of `get_closest_mob_direction` moves from `x, y, w, h` to `x1, y1, x2, y2`; expected directions unchanged |

## Proof

**Red, before the change.** The tests were run against the unchanged source, with the fixture change already applied. The `E` lines are in the scratchpad file `red74.txt` (sha256 prefix `ab688f5d8b4a`). 6 failed:

```
E   assert ((10, 20, 30, 40),) == ((10, 20, 40, 60),)             test_the_contour_path_returns_x1_y1_x2_y2 (path without a model returns x, y, w, h)
E   AssertionError: assert 'right' == 'left'                      test_a_mob_left_of_the_character_in_x1y1x2y2_is_to_the_left (centre read as 620)
E   test_direction_points_at_the_closest_mob[mobs0-left], [mobs2-right], [mobs3-left]   (new fixtures misread as x, y, w, h)
E   test_unidirectional_branch_derives_a_facing_from_the_on_screen_box                   (same)
```

The shared-centre tests in `test_smart_rotation_centres.py` pass before the change: `_smart_rotation_target` already computed `(x1 + x2) / 2`, so they pin the behaviour. They discriminate: temporarily replacing the centre with the `x, y, w, h` misreading `rect[0] + rect[2] / 2` turned the left-majority case red.

**Green, after.** `pytest` from the worktree root: `1316 passed, 3 skipped, 25 deselected`, 0 failed, 0 errors, 0 xfailed. `ruff check`, `ruff format` and `pyright` (0 errors) are clean on the changed files. The grep `rect[[01]] + rect[[23]] /` over `maple/` matches only `inventory.py`. `botting/controller/` is untouched.

## Could not verify

- **This changes which direction key reaches the game when a detection model is in use.** `get_closest_mob_direction` previously misread model boxes as `x, y, w, h`. It is correct by construction and by the offline geometry tests, but nothing offline shows the character facing the right mob in a live session. A person should watch one `mobs_hitting` rotation on a map with a detection model and confirm the character turns towards the nearest mob, and that smart rotation moves towards the side with more mobs.
- The model path (`extract_results`) was not run against a real YOLO result; the narrowing is a type change and an explicit four-element tuple, with the same `round` of the same values.
- The path without a model has no live user (`MapleMob` sets its hooks to `None`); its test uses a synthetic mob.
- The character's configs-only branch still returns `x, y, w, h`: follow-up #231.
