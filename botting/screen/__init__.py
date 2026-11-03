"""
Game-agnostic screen reading: finding a window, capturing it, exact sprite
matching and the Reading result.

`find_window` finds a window by its class and its process's executable;
`frame_source().grab(handle)` copies that window's client area, in physical
pixels, as a `Frame` that says whether it can be trusted.
"""

from botting.screen.capture import Frame, FrameSource, frame_source
from botting.screen.matching import (
    GlyphHit,
    Hit,
    find_glyphs,
    match,
    match_best,
    matches_at,
    read_glyphs,
)
from botting.screen.reading import Reading, Status
from botting.screen.window import MultipleWindows, WindowNotFound, find_window

__all__ = [
    "Frame",
    "FrameSource",
    "GlyphHit",
    "Hit",
    "MultipleWindows",
    "Reading",
    "Status",
    "WindowNotFound",
    "find_glyphs",
    "find_window",
    "frame_source",
    "match",
    "match_best",
    "matches_at",
    "read_glyphs",
]
