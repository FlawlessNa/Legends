"""
Owns the Windows timer period for this process.

Windows' default timer period is ~15.6ms, and `asyncio.sleep` inherits it: every
sleep wakes on the next tick, so a requested 1ms lands at ~15ms and a requested
33ms lands at ~42ms. The excess is *quantization*, not a per-await cost - it
shrinks as the request approaches a tick boundary and jumps as it crosses one -
so no single additive `OVERHEAD` can model it. That is the whole of issue #110:
`KeyboardInputWrapper.duration` is `sum(delays) + OVERHEAD * len(delays)`, an
additive model fitted against a quantized reality, and every truncation decision
in the tree rests on it.

`timeBeginPeriod(1)` raises the period for the *calling process* (Windows 10
2004 and later; system-wide on older builds), after which `asyncio.sleep` lands
within ~0.5ms of its request at every requested delay. That does not make the
overhead disappear - it makes it small and roughly constant, which is what the
additive model needs to be true rather than merely convenient.

The raise happens at import of `inputs_helpers`, before `OVERHEAD` is measured,
and is held for the life of the process. Two consequences worth stating:

- **Measured and spent in the same regime, by construction.** Raising it at
  Session start instead would leave `OVERHEAD` measured at import under the
  default period and then spent by a send loop running under a raised one - a
  precondition nothing in the send path could enforce, failing silently and in
  the under-estimating direction.
- **Every process that imports the input layer pays for it**, Engine processes
  and the test suite included, not just the one that sends. A 1ms timer costs
  interrupt rate and therefore power; on a machine running a game client that
  cost is already being paid by the client itself.
"""

import atexit
import ctypes
import logging

logger = logging.getLogger(__name__)

#: The period requested, in milliseconds. 1 is the floor Windows accepts and
#: what `_measure_send_loop_overhead` is calibrated against.
TIMER_PERIOD_MS: int = 1

#: `timeBeginPeriod` / `timeEndPeriod` return this on success.
_TIMERR_NOERROR: int = 0

_winmm = ctypes.WinDLL("winmm")
_winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
_winmm.timeBeginPeriod.restype = ctypes.c_uint
_winmm.timeEndPeriod.argtypes = [ctypes.c_uint]
_winmm.timeEndPeriod.restype = ctypes.c_uint

#: The period currently held, or None when this process holds none. Windows
#: reference-counts begin/end pairs, so this guard is what keeps the count at
#: most one however many times the raise is requested.
_held_period_ms: int | None = None


def raise_timer_resolution(period_ms: int = TIMER_PERIOD_MS) -> bool:
    """
    Raise this process' timer period, so `asyncio.sleep` lands near its request.

    Idempotent: a second call while a period is already held is a no-op rather
    than a second reference on Windows' count. Failure is logged and reported,
    never raised - a Session that cannot get a 1ms timer should still run, with
    an `OVERHEAD` measured under whatever period it did get.
    :param period_ms: Period to request, in milliseconds.
    :return: True if the period is now held by this process.
    """
    global _held_period_ms
    if _held_period_ms is not None:
        return True

    if _winmm.timeBeginPeriod(ctypes.c_uint(period_ms)) != _TIMERR_NOERROR:
        logger.warning(
            "timeBeginPeriod(%d) refused; sleeps stay quantized to the default "
            "~15.6ms tick and OVERHEAD will be measured against that.",
            period_ms,
        )
        return False

    _held_period_ms = period_ms
    atexit.register(restore_timer_resolution)
    return True


def restore_timer_resolution() -> None:
    """
    Release the period held by `raise_timer_resolution`, if any.

    Windows drops the request when the process exits, so this exists to pair
    the call rather than to prevent a leak; it is registered with `atexit` and
    is a no-op when nothing is held.
    """
    global _held_period_ms
    if _held_period_ms is None:
        return

    if _winmm.timeEndPeriod(ctypes.c_uint(_held_period_ms)) != _TIMERR_NOERROR:
        logger.warning("timeEndPeriod(%d) refused.", _held_period_ms)
    _held_period_ms = None


def held_timer_period_ms() -> int | None:
    """
    :return: The period this process holds, or None when it holds none.
    """
    return _held_period_ms
