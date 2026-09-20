"""
Curated Goldens: `docs/planning/movement-invariant-catalogue.md` -> **Golden**,
`CONTEXT.md`. One case per reachable movement type (via its fixture map), plus a
truncated plan, a Continuation pair, a Preemption at a mid-jump Step, and a telecast.

A Golden's cost is in reviewing it, so this covers a curated few - the Invariants in
`test_invariants.py` already run over the whole Corpus. Each case renders to a `.txt`
under `goldens/`: the **Hold table** `(key, t_down, t_up)` first, the form the
catalogue states every Invariant in, then the run-length collapsed timeline
`KeyboardInputWrapper.__str__` already produces below it, which catches a change to
Step *batching* the Holds are blind to. Both are quantized to 3dp.

**Nothing here is asserted about the +/-5% delay jitter** (`random_delay`,
`botting/controller/inputs/inputs_helpers.py`) - `SEED` pins it instead, so a case
renders byte-identically across a re-run and a diff means the compiled shape actually
changed, not that the RNG drew differently. Regenerate with
`python toolkit/movement_lab_sweep.py --golden <case>` (or `--all-goldens`) once a
change is known to be deliberate; a diff here is a review, not a chore.
"""

from __future__ import annotations

import contextlib
import importlib
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pytest

import botting.controller as controller_package
from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from maple.actions.movements_v2 import telecast
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics import movement_mechanics_v2
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.test_invariants import (
    _TELEPORT_SKILL,
    ACTION_DURATION,
    DIRECTIONS,
    _post_cancel_held,
    _post_completion_state,
    compile_record,
)

# `importlib.import_module`, not `import botting.controller.inputs.focused_inputs` or
# `from botting.controller.inputs import focused_inputs`: both of those resolve through
# attribute lookup on the `inputs` package, and `botting/controller/inputs/__init__.py`
# re-exports the `focused_inputs` *function* under that exact name, shadowing the
# submodule there - so either form silently hands back the function instead of the
# module (`tests/test_botting/test_preemption_direction_release.py` hits the same
# gotcha). Patching an attribute on the function would do nothing to the module-level
# `OVERHEAD` the class's methods actually read; only a `sys.modules` lookup, which
# `importlib.import_module` performs, reaches the real module object.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)
inputs_helpers_module = importlib.import_module(
    "botting.controller.inputs.inputs_helpers"
)

GOLDENS_ROOT = Path(__file__).parent / "goldens"

# `OVERHEAD` is measured from real wall-clock sleeps at process start
# (`inputs_helpers._measure_send_loop_overhead`), so two different Python processes -
# generating a golden, then verifying it - never measure quite the same value, and
# every duration in a rendered case is built from it. `SEED` alone cannot make a
# golden reproducible without also pinning this.
_FIXED_OVERHEAD = 0.001


@contextlib.contextmanager
def _deterministic_rendering() -> Iterator[None]:
    """
    Patches everything a rendered case's exact numbers depend on, and restores it on
    exit - **not** at module import, which would leak into every other test module in
    the same session once this one is collected (`OVERHEAD`'s real, per-process value
    is what `tests/test_botting/test_hold_derivation.py` and others assert against).

    Three `OVERHEAD` bindings, because each module reads its own: `inputs_helpers`
    (the source, and `_typematic_delay`'s generator closure, which reads it fresh at
    every `yield`), `focused_inputs` (`from .inputs_helpers import OVERHEAD` -
    `KeyboardInputWrapper.duration`/`holds`/`fill`/`truncate`), and the
    `botting.controller` re-export the movement builders read dynamically as
    `controller.OVERHEAD`. `key_binds` is patched too: goldens render offline and
    never legitimately want the real, gitignored, per-machine
    `configs/keybindings.ini`.

    Used both as this module's own `autouse` pytest fixture and, directly, by
    `movement_lab_sweep.py` - a standalone script with no pytest fixtures at all -
    around every case it renders.
    """
    original_overheads = (
        inputs_helpers_module.OVERHEAD,
        focused_inputs_module.OVERHEAD,
        controller_package.OVERHEAD,  # pyright: ignore[reportAttributeAccessIssue]
    )
    original_key_binds = movement_mechanics_v2.key_binds
    inputs_helpers_module.OVERHEAD = _FIXED_OVERHEAD  # pyright: ignore[reportAttributeAccessIssue]
    focused_inputs_module.OVERHEAD = _FIXED_OVERHEAD  # pyright: ignore[reportAttributeAccessIssue]
    controller_package.OVERHEAD = _FIXED_OVERHEAD  # pyright: ignore[reportAttributeAccessIssue]
    movement_mechanics_v2.key_binds = lambda ign: {"jump": "space"}
    try:
        yield
    finally:
        inputs_helpers_module.OVERHEAD = original_overheads[0]  # pyright: ignore[reportAttributeAccessIssue]
        focused_inputs_module.OVERHEAD = original_overheads[1]  # pyright: ignore[reportAttributeAccessIssue]
        controller_package.OVERHEAD = original_overheads[2]  # pyright: ignore[reportAttributeAccessIssue]
        movement_mechanics_v2.key_binds = original_key_binds


@pytest.fixture(autouse=True)
def _deterministic() -> Iterator[None]:
    with _deterministic_rendering():
        yield


# Arbitrary and fixed - only ever changed deliberately, together with every golden it
# affects. `random_delay` is a module-level generator drawing on the unseeded global
# `random` module, so without this every jittered Step's delay would differ on every
# run and no golden could ever match twice.
SEED = 20260914


@dataclass(frozen=True)
class _UltimateSkillStub(MapleSkill):
    """A `Skill` whose key bind does not go through the gitignored keybindings
    config - same shape as `test_invariants._StubTeleportSkill`."""

    key: str = field(default="f1", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


_ULTIMATE_SKILL = _UltimateSkillStub("Genesis", "Attack", animation_time=1.2)


def render_golden(wrapper: KeyboardInputWrapper) -> str:
    """The Hold table, then the run-length collapsed timeline. See the module
    docstring for why both are quantized to 3dp and what each half is for."""
    lines = ["Holds (key, t_down, t_up):"]
    for key in sorted(wrapper.holds):
        for t_down, t_up in wrapper.holds[key]:
            lines.append(f"  {key:<8} {t_down:.3f} {t_up:.3f}")
    lines.append("")
    lines.append(str(wrapper))
    return "\n".join(lines) + "\n"


def _map(name: str) -> corpus.CorpusMap:
    return next(e for e in corpus.CORPUS if e.name == name)


def _record(
    map_name: str, start: tuple[int, int], end: tuple[int, int]
) -> corpus.PlanRecord:
    entry = _map(map_name)
    return next(
        r for r in corpus.plans(entry) if r.pair.start == start and r.pair.end == end
    )


def _seeded_compile(
    record: corpus.PlanRecord, map_name: str, **kwargs: object
) -> KeyboardInputWrapper:
    random.seed(SEED)
    wrapper = compile_record(record, corpus.grid(_map(map_name)), **kwargs)  # type: ignore[arg-type]
    assert wrapper is not None
    return wrapper


# --- Case builders -------------------------------------------------------------------
#
# Each returns the case's full rendered text. `CASES` is what both this module and
# `toolkit/movement_lab_sweep.py` walk - the generator and the check share one source.

# name -> (map, start, end): the shortest reachable sample found to exercise that
# fixture's guaranteed movement type(s) (`corpus.FIXTURE_GUARANTEES`).
_MOVEMENT_TYPE_CASES: dict[str, tuple[str, tuple[int, int], tuple[int, int]]] = {
    "walk": ("walk_corridor", (17, 15), (14, 15)),
    "climb": ("ladder_climb", (20, 10), (20, 15)),
    "jump_left_right": ("jump_gap", (14, 11), (18, 11)),
    "jump": ("jump_ledge", (12, 15), (12, 12)),
    "enter_portal": ("portal_pair", (12, 35), (46, 5)),
    "teleport": ("teleport_shaft", (5, 19), (14, 19)),
    "narrow_jump": ("narrow_perch", (14, 15), (18, 13)),
}


def _case_movement_type(name: str) -> str:
    map_name, start, end = _MOVEMENT_TYPE_CASES[name]
    record = _record(map_name, start, end)
    wrapper = _seeded_compile(record, map_name)
    return render_golden(wrapper)


def _case_truncated_plan() -> str:
    """A plain multi-Step walk cut at production's `ACTION_DURATION`, landing on a
    boundary - the everyday case, deliberately not one of the atomic-component cuts
    `test_invariants.test_b1_truncation_integrity` files as a defect."""
    map_name = "walk_corridor"
    record = _record(map_name, (21, 15), (11, 15))
    wrapper = _seeded_compile(record, map_name, total_duration=ACTION_DURATION)
    return render_golden(wrapper)


def _case_continuation_pair() -> str:
    """`N` truncated at `ACTION_DURATION` carries `left` into `N+1` - a Continuation,
    per the catalogue's C-group note that the carry happens on truncation, not on a
    natural stop (which releases everything not forced first)."""
    map_name = "walk_corridor"
    n = _record(map_name, (27, 15), (12, 15))
    n_plus_1 = _record(map_name, (32, 15), (30, 15))
    full_n = _seeded_compile(n, map_name, total_duration=ACTION_DURATION)
    h0 = _post_completion_state(full_n)
    compiled = _seeded_compile(n_plus_1, map_name, initial_state=h0)
    return (
        f"N, truncated at ACTION_DURATION={ACTION_DURATION}s:\n\n"
        f"{render_golden(full_n)}\n"
        f"N+1, compiled against N's InputState ({h0}):\n\n"
        f"{render_golden(compiled)}"
    )


def _case_preemption_mid_jump() -> str:
    """The cut at `ACTION_DURATION` lands inside `JUMP_LEFT` here - one of
    `test_b1_truncation_integrity`'s filed findings, reused rather than restated. The
    Delivered Prefix is what a Preemption at this exact point would also produce;
    the note below it is the direction release D2 adds on the cancellation path,
    which a plain `truncate()` does not (see `focused_inputs`'s `finally` block)."""
    map_name = "ladder_climb"
    record = _record(map_name, (22, 19), (34, 8))
    cut = _seeded_compile(record, map_name, total_duration=ACTION_DURATION)
    remaining = _post_cancel_held(frozenset(cut.keys_held), cut.forced_key_releases)
    released_by_preemption = sorted((cut.keys_held & DIRECTIONS) - remaining)
    return (
        f"{render_golden(cut)}\n"
        f"Preemption at this cancel point additionally releases: "
        f"{released_by_preemption}\n"
    )


def _case_telecast() -> str:
    map_name = "teleport_shaft"
    record = _record(map_name, (5, 19), (14, 19))
    compiled = _seeded_compile(record, map_name)
    fused = telecast(compiled, corpus.LAB_IGN, _TELEPORT_SKILL, _ULTIMATE_SKILL)
    return render_golden(fused)


CASES: dict[str, Callable[[], str]] = {
    **{name: (lambda n=name: _case_movement_type(n)) for name in _MOVEMENT_TYPE_CASES},
    "truncated_plan": _case_truncated_plan,
    "continuation_pair": _case_continuation_pair,
    "preemption_mid_jump": _case_preemption_mid_jump,
    "telecast": _case_telecast,
}


@pytest.mark.parametrize("case", sorted(CASES), ids=sorted(CASES))
def test_golden(case: str) -> None:
    rendered = CASES[case]()
    golden_path = GOLDENS_ROOT / f"{case}.txt"
    assert golden_path.exists(), (
        f"No golden at {golden_path}; regenerate with "
        f"`python toolkit/movement_lab_sweep.py --golden {case}`."
    )
    expected = golden_path.read_text(encoding="utf-8")
    assert rendered == expected, (
        f"{golden_path.name} no longer matches. If this is a deliberate change, "
        f"regenerate with `python toolkit/movement_lab_sweep.py --golden {case}`."
    )
