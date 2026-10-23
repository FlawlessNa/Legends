---
ticket: 74
stage: plan
accepted_by: nassim
accepted_at: 2026-10-23
---

# Intent: one rectangle format for on-screen mobs

## Problem statement

`BaseMob.get_onscreen_mobs` returns mob rectangles in two formats, depending
on its path:
- **with a detection model** (the live configuration), `x1, y1, x2, y2`, from YOLO's box;
- **without one**, `x, y, w, h`, from `cv2.boundingRect`.

Its two consumers each assume a different format. `get_closest_mob_direction`
reads `x, y, w, h`, so with a detection model it computes a mob centre of
`x1 + x2/2`. For a mob at `x1=400, x2=440` that is 620, off to the right of
where the mob is, and the character faces the wrong way. `_smart_rotation_target`
reads `x1, y1, x2, y2`, which is wrong on the other path.

## Proposed outcome

`get_onscreen_mobs` returns `x1, y1, x2, y2` on both paths. That is what the model
path, `Character.get_onscreen_position` and `Box` already use, so only the
contour path converts. Every consumer reads that one format, and the standing
TODO in `mobs_hitting.py` is resolved.

## Affected users and systems

- `botting/models_abstractions/base_mob.py`.
- `maple/decision_makers/mixins/_mob_mixins.py` and `_rotation_mixins.py`.
- `maple/decision_makers/mobs_hitting.py` (the TODO).
- New unit tests.

The change can alter which direction key reaches the game: facing is chosen from
the closest mob's centre.

## Constraints

- No path here is on the `AGENTS.md` hard-stop list. `botting/controller/` is untouched.
- Proven offline with synthetic contours and rectangles. No client.

## Open questions

None. The maintainer asked for this ticket ("Yes, let's tackle #74",
2026-10-23). The issue body was written during #51, not by the maintainer.
