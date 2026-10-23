---
ticket: 74
stage: design
method: suite
criteria:
  - get_onscreen_mobs returns x1, y1, x2, y2 on both paths, and its docstring and return annotation say so
  - on the contour path, a synthetic image whose filtered contour has bounding rect x=10, y=20, w=30, h=40 yields (10, 20, 40, 60), with no client and no detection model
  - get_closest_mob_direction computes each mob's centre as ((x1 + x2) / 2, (y1 + y2) / 2), and on rectangles left and right of the character returns the side of the nearer centre
  - _smart_rotation_target's centre computation and get_closest_mob_direction's agree on the same synthetic rectangles, tested by feeding both the same list
  - for a mob at x1=400, x2=440 the computed centre x is 420, where today's get_closest_mob_direction gives 620
  - grep -rn "rect\[0\] + rect\[2\] /" maple/decision_makers finds nothing, so maple's mob consumers use a single convention (the inventory slot code in maple/model/interface is a different rectangle source and is out of scope)
  - the TODO about x1, y1, x2, y2 versus x, y, w, h in mobs_hitting.py is removed, and the comment it carried states the single format
  - no file under botting/controller/ changes, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
---

# Spec: one rectangle format for on-screen mobs

## Source

Issue #74 (part of #46).

## Shape

- **`BaseMob.get_onscreen_mobs`.** The contour path converts with
  `(x, y, x + w, y + h)` for each `cv2.boundingRect`. The model path is unchanged,
  because `extract_results` already returns `x1, y1, x2, y2`. The docstring's
  ":return:" says `x1, y1, x2, y2`.
- **`get_closest_mob_direction`.** It reads the centre as `((x1 + x2) / 2, (y1 + y2) / 2)`.
  Its docstring's "(x, y, w, h)" becomes "(x1, y1, x2, y2)".
- **`_smart_rotation_target`** already reads `(x1 + x2) / 2`, so it is unchanged
  except that its test pins it.
- **`mobs_hitting.py`.** The TODO goes, and the commented-out `w, h` lines with it.

## Verification method: suite

The red test is the centre computation: `get_closest_mob_direction` on
`[(400, 0, 440, 10)]` with the character between 420 and 620. Today it answers the
wrong side. The contour-path test is red too, since today it returns `(10, 20, 30, 40)`.

## Could not verify (for the PR)

**This changes which direction key reaches the game when a detection model is
in use.** The new answer is the correct one, by construction, but nothing
offline shows the character now faces the right mob in a live session.
Watching one `mobs_hitting` rotation on a map with a detection model would
confirm it.

## Not in scope

The inventory slot centre at `maple/model/interface/dynamic_components/inventory.py:106`.
It reads its own `boundingRect` correctly, as `x, y, w, h`.
