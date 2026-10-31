"""
Finding a window and capturing it: game-agnostic.

`find_window` finds a window by its class and its process's executable;
`frame_source().grab(handle)` copies that window's client area, in physical
pixels, as a `Frame` that says whether it can be trusted.
"""

from .capture import Frame, FrameSource, frame_source
from .window import MultipleWindows, WindowNotFound, find_window

__all__ = [
    "Frame",
    "FrameSource",
    "MultipleWindows",
    "WindowNotFound",
    "find_window",
    "frame_source",
]
