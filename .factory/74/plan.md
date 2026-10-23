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
  red_output_sha: see Proof below
  suite: null
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
