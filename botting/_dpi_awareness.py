"""
Declares per-monitor DPI awareness (v2) for this process, on import.

`botting/__init__.py` imports this before anything else, because it must come
before anything reads a window rectangle or a screen metric. From then on window
rectangles, `GetSystemMetrics`, the cursor and Desktop Duplication all agree in
physical pixels, whatever the monitor's scale. Without it, Windows hands a scaled
screen's coordinates to this process divided by the scale, and capture and
clicks land in different places.

A process can declare it only once: when something already did (a manifest, or
an earlier call), the call fails and is left alone.
"""

import ctypes

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, a pseudo-handle Windows defines as -4.
PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def declare() -> None:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return
    set_context = windll.user32.SetProcessDpiAwarenessContext
    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_int
    set_context(PER_MONITOR_AWARE_V2)


declare()
