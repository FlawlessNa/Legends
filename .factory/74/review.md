---
ticket: 74
stage: review
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 2d41a0e009f1c72cabca7fe2e5a873159c48fa69
---

# Review: one rectangle format for on-screen mobs

**Verdict: `pass`.** All eight criteria are met, and I observed the proof
myself rather than reading it off the plan. There are two non-blocking notes
(N1, N2) and one informational point (I1). The builder can fold N1 and N2
into the PR without another review cycle.

Diff reviewed: `git diff bc8065d..HEAD -- . ':!.factory'`, 8 files, against
`spec.md` (8 criteria), `spec-review-2.md` (notes a, b and c) and `plan.md`.

## Criteria

| # | Criterion (short) | Result | Evidence |
| --- | --- | --- | --- |
| 1 | `get_onscreen_mobs` returns x1, y1, x2, y2 on both paths, with a matching docstring and annotation `tuple[tuple[int, int, int, int], ...]` | **met** | `base_mob.py:50`: the annotation. `:54`: the docstring says "x1, y1, x2, y2 on both paths". `:71-74`: the contour path converts. The model path returns `extract_results`, which already returned x1, y1, x2, y2 and is now annotated to match (`in_game_visuals.py:405`) |
| 2 | A contour-path `BaseMob` subclass with rect 10, 20, 30, 40 yields `(10, 20, 40, 60)`, with `debug=False` and no client or model | **met** | `tests/test_botting/test_base_mob_rects.py`. The rectangle is drawn filled from (10, 20) to (39, 59), so `boundingRect` gives w=30 and h=40. `__init__` skips the model lookup. Red without the source: `((10, 20, 30, 40),) == ((10, 20, 40, 60),)` |
| 3 | `get_closest_mob_direction` uses `box_center`, and `((500, 5), [(400, 0, 440, 10)])` returns `"left"` | **met** | `_mob_mixins.py:80`. Red without the source: `assert 'right' == 'left'` |
| 4 | `_smart_rotation_target` uses `box_center`, and a `_RotationOwner`-style behaviour test puts the target on the side with more mobs | **met** (see N2) | `_rotation_mixins.py:230-232`, with the import at `:12` and no cycle (the suite collects). `test_smart_rotation_centres.py` is majority-left, using `(70, 40, 90, 70)`, as note b asks. It passes before and after the change, as a pin should. **The mutation goes red**: with the centre swapped for `rect[0] + rect[2] / 2`, the `[mobs0-left]` case fails `assert (60 < 50) == True` |
| 5 | The grep `rect\[[01]\] \+ rect\[[23]\] /` over `maple/` matches only `inventory.py` | **met** | The only match is `inventory.py:106`. Run over `botting/` and `toolkit/` too: no other matches |
| 6 | The TODO stays, narrowed to the configs-only character branch, and names #231 | **met** | `mobs_hitting.py:164-166`. It is accurate: `character.py` sets `res = detection_res` (from `_run_detection_methods`, which returns x, y, w, h) when there is no model. `_cross_validate_results` returns x1, y1, x2, y2, so "with detection configs and no model" is exactly the branch that is still wrong |
| 7 | The four fixtures and their comment move to x1, y1, x2, y2, the plan names it as a changed test, and the file passes | **met** | Each fixture is an exact conversion: `(0,40,20,30)` becomes `(0,40,20,70)`, and the other three likewise, so the centres are unchanged. No expected direction changed. The plan lists it under "Changed tests". The old fixtures against the new source: 3 failed, matching the spec's "three go red". New fixtures against the old source: they go red too (in the red run below) |
| 8 | Nothing under `botting/controller/` changes, and the full suite is green | **met** | Changed paths: `botting/models_abstractions`, `botting/visuals`, `maple/decision_makers` and `tests`. No controller file, ADR, `configs/maps/` file, `pyproject.toml` or dependency pin changed. Suite: `1316 passed, 3 skipped, 25 deselected`, with 0 failed, 0 errors and 0 xfailed |

## The proof, observed

- **Red.** I checked out the five source files at `bc8065d`, kept the HEAD tests, and ran the three test modules: **6 failed, 7 passed**.
  - The failures were the contour test (`(10, 20, 30, 40)`), the `"right" == "left"` test, `test_direction_points_at_the_closest_mob[mobs0-left]`, `[mobs2-right]` and `[mobs3-left]`, and `test_unidirectional_branch_...`.
  - That matches the plan's red list. I restored the files afterwards, and `git status` was clean.
- **Drift.** The rotation mutation above went red on the left-majority case only, which is the discriminating fixture. The right-majority case cannot discriminate (see note b in spec review 2), and it stayed green, as expected. Restored.
- **Green.** I ran `python -m pytest -q -p no:cacheprovider` from the worktree root: 1316 passed, 3 skipped (B3, cast_skill and B6, all pre-existing), 25 deselected. The flaky `test_truncate_lands_exactly_on_the_limit_for_a_multi_step_walk` (#229) passed on this run.
- **Static.** On the 8 touched files, `ruff check` passed, `ruff format --check` passed ("8 files already formatted"), and `pyright --pythonpath <venv python>` reported 0 errors, 0 warnings and 0 informations.

## `extract_results`: no runtime change

- **The values are the same.** Before: `tuple(map(round, dct["box"].values()))`. After: `x1, y1, x2, y2 = (round(v) for v in dct["box"].values())`, then `(x1, y1, x2, y2)`. That is the same `round`, of the same values, in the same order. In ultralytics 8.4.135, `Results.summary()` builds `box` by inserting `x1, y1`, then `x2, y2` (`engine/results.py`, around line 900). The name filter is unchanged.
- **The `mask` block is byte-identical.** It still unpacks `x1, y1, x2, y2 = pos` and removes boxes fully inside the masked region. The list is a `list` of tuples in both versions, so `vals.copy()` and `vals.remove(pos)` behave the same.
- **`Character` is unaffected.** `character.py:122-134` reads `len(found)` and assigns `found[0]` to a `Sequence[int] | None`, and a 4-tuple satisfies both. Its multi-detection branch re-reads `detections.summary()` itself and is untouched.
- See I1 for the one input where the two versions differ, which no live path produces.

## Other consumers of mob rectangles

I grepped the whole repo for `get_onscreen_mobs`, `get_mobs_positions_in_img`, `get_closest_mob_direction`, `extract_results` and `mobs_locations`, excluding the `_old` trees. The live consumers are:

- `get_mob_count` (`base_mob.py:85`), which only takes `len()`, so the format does not matter;
- `get_mobs_positions_in_img` (`_mob_mixins.py:33`), which passes the rectangles through;
- `_smart_rotation_target` (now on `box_center`);
- `MobsHitting._closest_mob_direction` (`mobs_hitting.py:221-225`), which feeds `get_closest_mob_direction`;
- `Character.get_onscreen_position`, through `extract_results`, covered above.

No other mob subclass overrides `_filter` or `_preprocess_img` for mobs. The other `boundingRect` users (`inventory.py`, `toolkit/hsv_filtering.py`) read their own rectangles and are out of scope. **No consumer was missed.**

## Notes

### N1 (minor): a dead suppression in a new test file

`tests/test_maple/test_smart_rotation_centres.py:71`:

```python
    return owner._smart_rotation_target()  # pyright: ignore[reportReturnType]
```

It suppresses nothing. I removed the comment and re-ran pyright on the file: **0 errors**. `_smart_rotation_target` is annotated `-> tuple[int, int]`, which is exactly `_target`'s return type. The typing rule in `AGENTS.md` is "fix them, don't suppress them". A dead ignore tells the next reader that the return type is wrong when it is not, and it would hide a real mismatch if the signature ever drifts. `reportUnnecessaryTypeIgnoreComment` is off, so no gate catches it. **Fix:** delete the comment. No other suppression was added. The ones in `test_mobs_hitting_direction.py:78` and `in_game_visuals.py:278-279, 331` predate this branch and sit on untouched lines.

### N2 (wording): criterion 4 says "built on the `_RotationOwner` fake"

The test declares its own `_Owner(MobsHittingMixin, NextTargetMixin)`, with its own `_Feature`, `_Minimap` and `_Map`. It does not reuse `_RotationOwner` from `tests/test_maple/test_rotation_target_handoff.py`. The shape is the same: the two mixins, `data` set in `__init__`, and `_create_rotation_attributes(smart_rotation=True, mob_count_threshold=2)`. The copy also needs things the original lacks: `map_area_width`, `vr_width`, and a stubbed `get_mobs_positions_in_img`. So the copy is a reasonable choice, and importing a private class from another test module would be worse. The observable the criterion protects, a discriminating majority-left test, is met and proven by the mutation. **Fix:** in the PR body (or the module docstring), say the fake follows `_RotationOwner`'s shape rather than importing it, so the deviation from the criterion's literal wording is recorded, not discovered.

### I1 (informational, no action)

`extract_results` now raises `ValueError` on unpacking if a `box` has a coordinate count other than four. That would happen with an oriented-box (OBB) model, whose `box` has `x1..x4` and `y1..y4`. Before, with no mask, it returned an 8-tuple. Every consumer already unpacks four values (`box_center`, the `mask` block, `Character`'s `x, y, w, h = res`), so an OBB model failed downstream before too. The failure now happens one frame earlier, in the same call chain. No OBB model is in use.

## The PR's *Could not verify*: accurate

The plan's section, which feeds the PR body, leads with "**This changes which direction key reaches the game when a detection model is in use.**" That is the real risk of this diff. `get_closest_mob_direction` drives the facing key in `MobsHitting`'s unidirectional branch, and on the live (model) path its answer changes for any mob whose misread centre landed on the other side of the character. The section also names:

- the human check: one `mobs_hitting` rotation on a map with a detection model;
- that `extract_results` was not run on a real YOLO result;
- that the contour path has no live user;
- the #231 follow-up.

It is neither understated nor padded. The one item it asks a human to watch that this diff does not change is smart rotation: on the model path it already read x1, y1, x2, y2, and only the contour path, which has no live user, changes for it. Watching it is harmless, but the PR should not imply that smart rotation's live behaviour moved.

**Note c from spec review 2** (the approved intent was corrected: the TODO was not resolved, and the character's box is not consistent on the configs-only branch) is recorded in `plan.md` under "Notes from the passing spec review", marked "for the PR body". **The PR body must carry it.** I could not check that, because no PR exists yet.

## Invariants and ADRs

- The diff does not touch movement compilation or input dispatch, so it bears on no catalogue invariant (A*, B*, D*).
- No ADR governs mob detection or facing. ADR 0002 (the input path) is not touched: the facing key still leaves through the existing `MobsHitting` path, and only the choice of direction changes.
- Layering is intact: `maple/.../_rotation_mixins.py` imports `maple/.../_mob_mixins.py`, and nothing in `botting/` gained a `maple` import.
- Vocabulary: no new domain term is introduced.

## What a human must still do

1. Watch one `mobs_hitting` session on a map with a mob detection model, and confirm the character turns to face the nearest mob, including one standing slightly left of the character. That is the case this fix flips.
2. Check that the PR body carries note c (the intent correction) and the *Could not verify* section above.

## What this review could not verify

- No game client was run, so the live facing behaviour is unobserved (see above).
- `extract_results` was checked by reading it against the ultralytics 8.4.135 source, not by running a real YOLO `Results` through it.
- The PR body does not exist yet, so I judged the plan's *Could not verify* and note c as the text the PR will carry, not the PR itself.
- Pyright printed "venv .venv subdirectory not found" and fell back to `--pythonpath`. Imports resolved (0 errors, with no `reportMissingImports`), but the hook's own invocation may differ.
