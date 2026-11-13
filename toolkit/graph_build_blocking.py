"""
How long the decision loop is blocked while a foothold graph builds (#430).

A graph takes seconds to build, and the character's stats change it. This
script runs what an Engine runs, an asyncio loop, with a heartbeat that wakes
every `HEARTBEAT` seconds and a planning step every `DECISION_INTERVAL`, and
times the longest stretch the loop went without running, in two modes:

- **before** (#396): the planning step builds the graph itself, inside the
  loop, the first time and after the stat change, as the lazy
  `MovementHandler.graph` did;
- **after** (#430): the step asks `FootholdGraphs.ready`, which builds in a
  worker thread, and plans a Path only once the graph is there.

Each run does what a Session does: a graph for the profile's stats (jump
×1.0), then the stat changes (jump ×1.2, a buff) and the next one is built.

    python -m toolkit.graph_build_blocking
    python -m toolkit.graph_build_blocking --map "Damp Forest" --no-teleport

It needs the game data store (`data/game_data`). It sends no keys and opens no
window.
"""

import argparse
import asyncio
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from maple.model.mechanics.physics import VRPhysics, game_physics
from maple.model.navigation import FootholdGraph, FootholdGraphs
from maple.model.world import Platform, WorldMap

#: How often the heartbeat asks to wake, in seconds.
HEARTBEAT = 0.005
#: How often the planning step runs: the `path` attribute's refresh threshold.
DECISION_INTERVAL = 0.1
#: The stats a run builds graphs for, in order: the profile's, then a buff's.
JUMP_MULTIPLIERS = (1.0, 1.2)
MAPS = ("Victoria Road: Ellinia", "Damp Forest")


@dataclass
class Run:
    """What one run measured, in seconds."""

    map_name: str
    mode: str
    teleport: bool
    #: The wall time of each graph's build, as the planning step saw it.
    builds: list[float] = field(default_factory=list)
    #: Each heartbeat's lateness past its `HEARTBEAT`: the loop blocked.
    gaps: list[float] = field(default_factory=list)
    #: The longest planning step.
    longest_step: float = 0.0

    @property
    def longest_block(self) -> float:
        return max(self.gaps, default=0.0)

    def row(self) -> str:
        p99 = (
            statistics.quantiles(self.gaps, n=100)[98]
            if len(self.gaps) >= 100
            else self.longest_block
        )
        builds = " / ".join(f"{b:.2f}" for b in self.builds)
        return (
            f"{self.map_name:<24} {'yes' if self.teleport else 'no':<8} "
            f"{self.mode:<7} {builds:<12} {self.longest_block * 1000:>9.1f} "
            f"{p99 * 1000:>8.1f} {self.longest_step * 1000:>10.1f}"
        )


HEADER = (
    f"{'map':<24} {'teleport':<8} {'mode':<7} {'build s':<12} "
    f"{'block ms':>9} {'p99 ms':>8} {'step ms':>10}"
)


def physics_list(values: dict[str, float]) -> list[VRPhysics]:
    return [
        VRPhysics.from_game_files(values, jump_multiplier=m) for m in JUMP_MULTIPLIERS
    ]


async def _heartbeat(run: Run, stop: asyncio.Event) -> None:
    last = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(HEARTBEAT)
        now = time.perf_counter()
        run.gaps.append(max(0.0, now - last - HEARTBEAT))
        last = now


async def _drive(
    run: Run, step: Callable[[VRPhysics], bool], stats: Sequence[VRPhysics]
) -> None:
    """Runs `step` every decision interval, until it has a graph for each stat."""
    stop = asyncio.Event()
    beat = asyncio.create_task(_heartbeat(run, stop))
    await asyncio.sleep(10 * HEARTBEAT)
    for physics in stats:
        asked = time.perf_counter()
        while True:
            started = time.perf_counter()
            done = step(physics)
            run.longest_step = max(run.longest_step, time.perf_counter() - started)
            if done:
                break
            await asyncio.sleep(DECISION_INTERVAL)
        run.builds.append(time.perf_counter() - asked)
        # The stat changes in a later cycle, not in this one.
        await asyncio.sleep(DECISION_INTERVAL)
    await asyncio.sleep(10 * HEARTBEAT)
    stop.set()
    await beat


def measure(
    world_map: WorldMap, values: dict[str, float], *, teleport: bool, mode: str
) -> Run:
    """
    One run on `world_map`, in `mode` `"before"` or `"after"`.

    The step plans a Path between the first platform's middle and the last's
    once the graph is there, so the time A* takes on the loop is counted too.
    """
    run = Run(world_map.name, mode, teleport)
    stats = physics_list(values)
    start = _middle(world_map.platforms[0])
    goal = _middle(world_map.platforms[-1])

    if mode == "before":
        built: dict[VRPhysics, FootholdGraph] = {}

        def step(physics: VRPhysics) -> bool:
            graph = built.get(physics)
            if graph is None:
                graph = built[physics] = FootholdGraph.build(
                    world_map, physics, teleport=teleport
                )
            _path(graph, start, goal)
            return True

    elif mode == "after":
        graphs = FootholdGraphs(world_map, teleport=teleport)

        def step(physics: VRPhysics) -> bool:
            graph = graphs.ready(physics)
            if graph is None:
                return False
            _path(graph, start, goal)
            return True

    else:
        raise ValueError(f"unknown mode {mode!r}")

    asyncio.run(_drive(run, step, stats))
    return run


def _middle(platform: Platform) -> tuple[float, float]:
    x = (platform.left + platform.right) / 2
    y = platform.y_at(x)
    assert y is not None
    return (x, y)


def _path(
    graph: FootholdGraph, start: tuple[float, float], goal: tuple[float, float]
) -> None:
    try:
        graph.path(start, goal)
    except ValueError:
        pass  # off every surface: the cost of trying is what is timed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", action="append", dest="maps", help="game map name")
    parser.add_argument(
        "--no-teleport", action="store_true", help="only build without teleport moves"
    )
    parser.add_argument(
        "--mode", choices=("before", "after"), action="append", dest="modes"
    )
    args = parser.parse_args(argv)
    values = game_physics()
    teleports = (False,) if args.no_teleport else (False, True)
    print(HEADER)
    for name in args.maps or MAPS:
        world_map = WorldMap.load(name)
        for teleport in teleports:
            for mode in args.modes or ("before", "after"):
                print(
                    measure(world_map, values, teleport=teleport, mode=mode).row(),
                    flush=True,
                )
    print(
        "\nblock: the longest the loop went without running; p99: of every "
        f"{HEARTBEAT * 1000:.0f} ms heartbeat's lateness; step: the longest planning "
        "step; build: each stat's time from asked to planned "
        f"(jump x{' then x'.join(str(m) for m in JUMP_MULTIPLIERS)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
