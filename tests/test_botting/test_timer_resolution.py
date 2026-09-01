"""
`OVERHEAD` and the timer period it is measured under (issue #110).

`KeyboardInputWrapper.duration` is `sum(delays) + OVERHEAD * len(delays)` - an
*additive* model - and every truncation decision rests on it. Under Windows'
default ~15.6ms timer period that model is fitted against a quantized reality:
the excess over a requested sleep is ~13ms at a 1ms request and ~9ms at a 33ms
one, so no single constant fits and `duration` is wrong at every Step.

These tests assert the two halves of the fix, both as *measured gaps* - which is
what the ticket names as the acceptance criterion, and the only thing that can
be observed. `NtQueryTimerResolution` is not usable here: it reports the
system-global period, which any other process on the machine may have raised,
and says nothing about the period *this* process actually runs under.

Timing assertions are medians over a sample, and the two regimes they separate
differ by an order of magnitude (~1.3ms against ~14.5ms at a 1ms request), so
the thresholds sit several times clear of both.
"""

import asyncio
import statistics
import time
from collections.abc import Generator

import pytest

from botting.controller.inputs.inputs_helpers import DELAY, OVERHEAD
from botting.controller.inputs.timer_resolution import (
    TIMER_PERIOD_MS,
    held_timer_period_ms,
    raise_timer_resolution,
    restore_timer_resolution,
)

#: Sleeps per measurement. Small enough that the whole module stays near a
#: second, large enough for the median to shrug off a scheduling outlier.
SAMPLES = 25

#: The requests swept. Spans two orders of magnitude on purpose: quantization
#: shows up as the excess *changing* across them, which is exactly what an
#: additive constant cannot express.
REQUESTS = (0.001, 0.005, 0.0215, DELAY)

#: A requested sleep must land inside this much of its request. The default
#: period puts the floor at ~15.6ms, so anything under it fails there.
MAX_EXCESS = 0.005

#: How much the excess may vary across `REQUESTS` before the additive model is
#: a misfit. Measured at ~2.8ms under the default period, ~0.5ms raised.
MAX_EXCESS_SPREAD = 0.002


def _median_gap(requested: float, samples: int = SAMPLES) -> float:
    """
    The wall-clock gap `focused_inputs` actually pays for one Step's delay.

    Measured inside a single running loop, like the send loop's - not with one
    `asyncio.run` per sleep, which charges every Step an event loop's startup.
    """

    async def _measure() -> float:
        await asyncio.sleep(requested)  # discard: a fresh loop's one-off costs

        gaps: list[float] = []
        for _ in range(samples):
            start = time.perf_counter()
            await asyncio.sleep(requested)
            gaps.append(time.perf_counter() - start)
        return statistics.median(gaps)

    return asyncio.run(_measure())


@pytest.fixture
def raised_period() -> Generator[None]:
    """
    Puts the process' timer period back however the test left it.

    Nothing here should run unraised - `inputs_helpers` raises at import and the
    timing tests below depend on it - so a test that releases the period must
    not leak that to whatever runs next.
    """
    yield
    raise_timer_resolution()


# --- The period this process holds ------------------------------------------


def test_importing_the_input_layer_raises_the_timer_period() -> None:
    """
    The raise is an import-time side effect of `inputs_helpers`, deliberately:
    `OVERHEAD` is measured at import, so raising it later - at Session start,
    say - would measure the constant under one period and spend it under
    another, with nothing in the send path able to catch the mismatch.
    """
    assert held_timer_period_ms() == TIMER_PERIOD_MS


def test_raising_an_already_held_period_is_a_no_op() -> None:
    assert raise_timer_resolution() is True
    assert held_timer_period_ms() == TIMER_PERIOD_MS


def test_the_period_can_be_released_and_re_raised(raised_period: None) -> None:
    restore_timer_resolution()
    assert held_timer_period_ms() is None

    assert raise_timer_resolution() is True
    assert held_timer_period_ms() == TIMER_PERIOD_MS


# --- The gaps the send loop actually pays -----------------------------------


def test_a_short_sleep_is_not_quantized_to_the_default_timer_tick() -> None:
    """
    The sharpest reading of the defect. Under the default ~15.6ms period a 1ms
    `asyncio.sleep` cannot return before the next tick, so it takes ~14.5ms -
    fourteen times what it asked for, and nothing additive describes that.
    """
    excess = _median_gap(0.001) - 0.001

    assert excess < MAX_EXCESS


def test_a_step_sized_sleep_lands_near_its_request() -> None:
    """One Step's delay - what a walk pays ~150 times over."""
    excess = _median_gap(DELAY) - DELAY

    assert excess < MAX_EXCESS


def test_the_excess_does_not_depend_on_the_requested_delay() -> None:
    """
    What makes `OVERHEAD` a constant at all. Quantization is not additive: it
    shrinks as a request approaches a tick boundary and jumps as it crosses
    one, so under the default period the excess ranges over ~2.8ms across
    `REQUESTS` and no single value fits any of them.
    """
    excesses = [_median_gap(request) - request for request in REQUESTS]

    assert max(excesses) - min(excesses) < MAX_EXCESS_SPREAD


def test_overhead_is_a_running_loop_residual_not_an_event_loop_startup() -> None:
    """
    `_get_asyncio_overhead` timed `asyncio.run(...)` per iteration, so the
    constant carried a whole loop's startup and teardown - a cost the send loop
    pays once per Action, not once per Step. That put it at ~11.5ms against a
    true per-Step residual of ~0.5ms.
    """
    assert 0.0 <= OVERHEAD < MAX_EXCESS


def test_overhead_predicts_the_gap_it_models() -> None:
    """
    The claim `duration` makes, at the granularity it makes it: a Step's
    wall-clock cost is its delay plus `OVERHEAD`.
    """
    for request in REQUESTS:
        predicted = request + OVERHEAD

        assert abs(_median_gap(request) - predicted) < MAX_EXCESS_SPREAD
