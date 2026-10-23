---
ticket: 74
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "_smart_rotation_target computes its mob centres with MobsHittingMixin.box_center too, and a behaviour test built on the _RotationOwner fake, with x1, y1, x2, y2 mob rectangles left and right of the character, gets the target on the side the mobs are on"
---

# Spec review, cycle 2: one rectangle format for on-screen mobs

**Verdict: `pass`.** I checked only the seven findings from `spec-review.md`,
against `spec.md` at `a992d7b`. All seven are resolved at the level of the
criteria. Three notes remain. The plan must settle all three, and none of them
changes what a criterion requires:

- **Note a:** pyright *does* force `extract_results` to narrow. I checked it.
- **Note b:** criterion 4's "the side the mobs are on" needs a tie-break rule,
  and a fixture that actually discriminates.
- **Note c:** the intent still says the TODO is resolved.

## 1. The TODO: resolved

Criterion 6 keeps the TODO, narrowed to what is still true. In the
configs-only branch, `Character.get_onscreen_position` returns `x, y, w, h`.
The criterion names #231. I read #231: it is open, it describes that branch
correctly, and it keeps the measured offset out of its own scope, as
`ready-for-human` work. "What changed after approval" records why the
revision was made.

**Note c: the intent and the spec now disagree on one sentence.** `intent.md`
still says "the standing TODO in `mobs_hitting.py` is resolved". The intent
also says `Character.get_onscreen_position` "already use[s]" `x1, y1, x2, y2`.
The spec overrides both, and says so. This is not one of the four things the
maintainer owns (`docs/factory/README.md`). It does not touch a hard-stop path,
and it narrows the change rather than widening it. So it was this stage's to
decide, and it has been recorded. **The PR body must name it**, so that the
maintainer sees the approved intent was corrected and does not discover it.

## 2. The changed test file: resolved

Criterion 7 names the file, the four fixtures, the comment, and the moved
behaviour: the input format of `get_closest_mob_direction`. The Verification
section says three tests go red without the fixture change, and that the
expected directions stay the same. That matches what I computed in cycle 1.

## 3. Shared centres: resolved, with one wording gap

Both consumers now take their centres from `MobsHittingMixin.box_center`.
That is checkable by reading the code. Every `_smart_rotation_target` owner
inherits `MobsHittingMixin`. `_rotation_mixins.py` can import from
`_mob_mixins.py` without a cycle, because `_mob_mixins.py` imports only from
`botting`.

**Note b: criterion 4's observable has two gaps.**

- **Mobs on both sides.** With rectangles "left and right of the character",
  "the side the mobs are on" has no single answer. `_smart_rotation_target`
  takes a **majority vote**, and a tie goes right (`len(left_x) > len(right_x)`,
  else right). The plan must state the expected side as "the side with more
  mobs", and keep the fixture away from a tie.
- **A fixture that cannot tell the formats apart.** The test is a pin, green
  before and after. It only guards against drift if at least one of its
  fixtures would flip side under an `x, y, w, h` misreading.
  - The misreading, `x1 + x2 / 2`, only ever moves a centre further right. So
    a mob on the right can never flip, and only a mob on the **left** can
    discriminate.
  - With the character centred at x 100, `(70, 40, 90, 70)` does: read
    correctly its centre is 80 (left), misread it is 115 (right).
  - The plan must make the majority side left, using mobs like that one.
    Without one, the behaviour test passes against either convention.

## 4. The annotation: resolved, and `extract_results` must narrow

Criterion 1 names `tuple[tuple[int, int, int, int], ...]`. The Shape puts the
narrowing of `extract_results` in scope "if pyright requires it".

**Note a: it does.** I ran pyright 1.1.411 from the venv on a scratch file
with these signatures. Returning a `tuple[Sequence[int], ...]`, which is
today's `extract_results`, from a function annotated
`tuple[tuple[int, int, int, int], ...]` is a `reportReturnType` error.

Narrowing `extract_results` itself has a further trap.
`tuple(map(round, dct["box"].values()))` infers `tuple[int, ...]`, and that
also fails against a 4-tuple, with "Tuple size mismatch". It needs an explicit
four-element construction. The contour path's
`x, y, w, h = cv2.boundingRect(c); (x, y, x + w, y + h)` type-checks clean.

So the plan's radius must list `botting/visuals/in_game_visuals.py`
unconditionally, not "if needed". The radius has to be named before any file
is touched.

Today, pyright reports 0 errors, 0 warnings and 0 informations on all four
touched files: `in_game_visuals.py`, `base_mob.py`, `_mob_mixins.py` and
`_rotation_mixins.py`. Touching them surfaces nothing pre-existing.
`Character` reads `found[0]` into a `Sequence[int] | None`, which still accepts
the narrowed type.

## 5. The contour test: resolved

Criterion 2 now says "called with `debug=False`" and "a test subclass of
`BaseMob`". The Shape states that the path is a contract, not a live path,
because `MapleMob` sets both hooks to `None`.

## 6. The grep: resolved

I ran `grep -rnE "rect\[[01]\] \+ rect\[[23]\] /" maple/` on today's tree. It
matches two lines:

- `_mob_mixins.py:80`, the bug;
- `inventory.py:106`, the allowed hit.

It does not match `_rotation_mixins.py:229`, which moves onto `box_center`
anyway. After the change, the criterion's "matches only inventory.py" is
mechanical.

## 7. The red test: resolved

`get_closest_mob_direction((500, 5), [(400, 0, 440, 10)])` returns `"right"`
today, because the centre is read as `(620, 5)`. Under `box_center` the centre
is `(420, 5)` and the answer is `"left"`. The criterion states exactly that.

## Out of scope, as agreed

The contour path ignoring `mask` is listed under "Not in scope". I did not
re-review it.

## What this review could not verify

- I did not run pytest. The three red fixture tests are still computed, not
  observed.
- The pyright result in note a comes from a scratch file that mirrors the
  signatures, not from an implementation.
- What I said in cycle 1 still stands: I did not confirm that any current
  launcher runs with no Character model loaded.
