"""
Visualizes a KeyboardInputWrapper as a Gantt-style key-hold timeline.

Each row is a unique key; each bar is a continuous hold interval.
Forced key releases are marked with a red dashed line at the end of the timeline.
Hold duration (in seconds) is printed inside each bar when wide enough to fit.

Import usage:
    from toolkit.movement_timeline import visualize
    visualize(wrapper, title="Walk Right -> Jump Left")

Standalone demo:
    python -m toolkit.movement_timeline
"""

from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from botting.controller import KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD

_KEY_COLORS = {
    "left": "#4C72B0",
    "right": "#DD8452",
    "up": "#55A868",
    "down": "#C44E52",
}
_PREFERRED_ORDER = ["up", "down", "left", "right"]
_DEFAULT_COLOR = "#8172B2"
_MIN_BAR_WIDTH_FOR_LABEL = 0.035  # seconds
_TIMELINE_X_MAX = 5.0  # fixed x-axis range (seconds) — change here to rescale


def _parse_intervals(
    wrapper: KeyboardInputWrapper,
) -> dict[str, list[tuple[float, float]]]:
    """
    Walk the wrapper's event list and produce per-key hold intervals.

    Returns {key_name: [(t_down, t_up), ...]} in event order.
    Simultaneous events (list keys/events) are all timestamped at the same t.
    Keys still held at the end of the wrapper are closed at wrapper.duration.
    """
    t = 0.0
    held: dict[str, float] = {}  # key -> time it went down
    intervals: dict[str, list[tuple[float, float]]] = {}

    for key_or_list, event_or_list, delay in zip(
        wrapper.keys, wrapper.events, wrapper.delays
    ):
        pairs: list[tuple[str, str]] = (
            [(key_or_list, event_or_list)]
            if isinstance(key_or_list, str)
            else list(zip(key_or_list, event_or_list))
        )
        for key, event in pairs:
            intervals.setdefault(key, [])
            if event == "keydown" and key not in held:
                held[key] = t
            elif event == "keyup" and key in held:
                intervals[key].append((held.pop(key), t))

        t += delay + OVERHEAD

    for key, t_down in held.items():
        intervals.setdefault(key, []).append((t_down, t))

    return intervals


def visualize(
    wrapper: KeyboardInputWrapper,
    title: str = "Key Input Timeline",
    save_path: str | None = None,
    show: bool = True,
    block: bool = True,
    fig: plt.Figure | None = None,
) -> plt.Figure | None:
    """
    Render a Gantt chart of key-hold intervals from a KeyboardInputWrapper.

    Parameters
    ----------
    wrapper:    The KeyboardInputWrapper to visualize.
    title:      Plot title (shown above the chart).
    save_path:  If given, save the figure to this path (PNG/SVG/etc.).
    show:       If True, open/refresh the interactive window.
    block:      If True, block until the window is closed (ignored when fig is given).
    fig:        If given, clear and redraw this existing figure in place rather than
                creating a new window.
    """
    intervals = _parse_intervals(wrapper)
    if not intervals:
        print("No key events found in wrapper.")
        return fig

    all_keys = list(intervals)
    ordered = [k for k in _PREFERRED_ORDER if k in all_keys]
    ordered += sorted(k for k in all_keys if k not in ordered)
    n = len(ordered)

    total = wrapper.duration
    updating = fig is not None
    if not updating:
        fig_w = _TIMELINE_X_MAX * 4
        fig_h = n * 0.9 + 2.2
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    else:
        fig.clear()
        ax = fig.add_subplot(111)

    for lane, key in enumerate(ordered):
        color = _KEY_COLORS.get(key, _DEFAULT_COLOR)
        for t_start, t_end in intervals[key]:
            width = max(t_end - t_start, 0.003)
            ax.barh(
                lane,
                width,
                left=t_start,
                height=0.55,
                color=color,
                alpha=0.85,
                edgecolor="white",
                linewidth=0.5,
            )
            if width >= _MIN_BAR_WIDTH_FOR_LABEL:
                ax.text(
                    t_start + width / 2,
                    lane,
                    f"{width:.3f}s",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white",
                    fontweight="bold",
                )

    # Forced releases: red dashed vertical line at wrapper.duration per key
    forced = set(wrapper.forced_key_releases)
    if forced:
        ax.axvline(
            total,
            color="red",
            linestyle="--",
            linewidth=1.2,
            alpha=0.7,
            label=f"forced release: {', '.join(sorted(forced))}",
        )
        for key in forced:
            if key in ordered:
                lane = ordered.index(key)
                ax.plot(
                    total,
                    lane,
                    marker="x",
                    color="red",
                    markersize=8,
                    markeredgewidth=1.5,
                    zorder=5,
                )

    ax.set_yticks(range(n))
    ax.set_yticklabels(ordered, fontsize=11)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0.0, _TIMELINE_X_MAX)
    ax.set_xlabel("Time (s)", fontsize=11)
    ax.set_title(
        f"{title}\n"
        f"duration={total:.3f}s   "
        f"events={len(wrapper.keys)}   "
        f"forced_releases={sorted(forced) or 'none'}",
        fontsize=12,
    )
    ax.grid(axis="x", linestyle="--", alpha=0.35)

    legend_patches = [
        mpatches.Patch(color=_KEY_COLORS.get(k, _DEFAULT_COLOR), label=k)
        for k in ordered
    ]
    if forced:
        legend_patches.append(
            mpatches.Patch(
                color="red", label=f"forced release: {', '.join(sorted(forced))}"
            )
        )
    ax.legend(handles=legend_patches, loc="upper right", fontsize=9, framealpha=0.7)

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved to {save_path}")

    if updating:
        fig.canvas.draw_idle()
        return fig

    if show:
        plt.show(block=block)
    if block:
        plt.close(fig)
        return None
    return fig


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def _build_demo_wrapper() -> KeyboardInputWrapper:
    """
    Build a sample wrapper without a live game window.

    Sequence: walk right (12 ticks) → jump left (hold left through arc) → walk right (8 ticks).
    Uses handle=0; safe as long as no movement keys are physically held on the keyboard.
    The jump key is represented as 'z' (replace with actual bind as needed).
    """
    _TICK = 0.033

    w = KeyboardInputWrapper(handle=0)

    for _ in range(12):
        w.append("right", "keydown", _TICK)
    w.append("right", "keyup", _TICK * 2)

    # Simultaneous left + jump key press
    w.append(["left", "z"], ["keydown", "keydown"], _TICK)
    w.append("z", "keyup", 0.75)
    w.append("left", "keyup", _TICK)

    for _ in range(8):
        w.append("right", "keydown", _TICK)
    w.append("right", "keyup", _TICK)

    w.forced_key_releases.append("z")
    return w


if __name__ == "__main__":
    demo = _build_demo_wrapper()
    print(demo)
    print()
    visualize(demo, title="Demo: Walk Right -> Jump Left -> Walk Right")
