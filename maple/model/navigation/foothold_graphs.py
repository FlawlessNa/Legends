"""
`FootholdGraphs`: a map's `FootholdGraph`s, one per `VRPhysics`, built in a
worker thread so that building one never stalls the decision loop (#430).

**Why off the loop.** A graph takes seconds to build (2.2 s on Ellinia, 3.6 s
with teleport, measured offline in #396), and it depends on the jump arc, so
a change of the character's speed or jump stats needs a new one. Built inside
a DecisionMaker's `_decide`, it blocked the Engine's event loop, and every
DecisionMaker sharing it, for that long.

**Why a thread, not a process.** `toolkit/graph_build_blocking.py` measures
the longest the event loop goes without running while a graph builds. In a
worker thread the build only shares the GIL with the loop, which gets it back
within the interpreter's switch interval (5 ms): on Ellinia the longest stall
was 7 to 12 ms, against 2.3 s (3.7 s with teleport) built on the loop. A
process would also take the CPU off the Engine's core, but costs a second
interpreter's memory and a pickled copy of the map and the graph each way,
for a stall the thread already keeps under a decision interval.

**Asking for a graph never blocks the caller** (`ready`). It returns the
graph when it is built, and otherwise starts building it and returns `None`:
the caller holds. Only a whole graph is ever returned: it is stored once
`FootholdGraph.build` has returned, so no Path is planned on a half-built one.
`graph` blocks, for offline callers (the movement lab, tests, tooling).

**Latest wins.** One graph builds at a time. Asked for several while one
builds, only the last one asked is built next: stats that changed twice
during a build need no graph for the values in between.

`LRU` graphs are kept, so a stat that flips back (a buff on, then off) costs
nothing.

**A build that raises is tried again after a back-off**: `RETRY_AFTER`
seconds, doubled at each failure up to `RETRY_MAX`. Each failure is logged at
`ERROR` with its traceback, its attempt and when it is tried next. Until then
those stats hold, and nothing is built every cycle. A transient failure (a
`MemoryError` on a loaded machine) recovers; a bug keeps logging, at most
every `RETRY_MAX`.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import NamedTuple

from botting import PARENT_LOG
from maple.model.mechanics.physics import VRPhysics
from maple.model.world import WorldMap

from .foothold_graph import FootholdGraph

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class _Failure(NamedTuple):
    """The last failed build of one set of physics."""

    attempts: int
    retry_at: float  # on `FootholdGraphs`' clock


class FootholdGraphs:
    """
    A map's foothold graphs, one per `VRPhysics`, built in a worker thread.

    :ivar world_map: The map the graphs are built on.
    :ivar teleport: Whether the graphs hold teleport moves.
    """

    #: How many graphs are kept, the most recently asked for first.
    LRU = 2
    #: Seconds before a failed build is tried again, doubled at each failure.
    RETRY_AFTER = 10.0
    #: The longest wait between two tries of a failing build, in seconds.
    RETRY_MAX = 300.0

    def __init__(
        self,
        world_map: WorldMap,
        *,
        teleport: bool,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        :param clock: Seconds, for the retry back-off; tests pass their own.
        """
        self.world_map = world_map
        self.teleport = teleport
        self._clock = clock
        self._lock = threading.Lock()
        self._built = threading.Condition(self._lock)
        self._graphs: OrderedDict[VRPhysics, FootholdGraph] = OrderedDict()
        # The physics asked for last and not built yet, which the worker builds
        # next; and the physics it is building now.
        self._wanted: VRPhysics | None = None
        self._building: VRPhysics | None = None
        # Physics whose last build raised, and when to try again: not every
        # cycle, so a bug in the build doesn't rebuild and log at each one.
        self._failed: dict[VRPhysics, _Failure] = {}
        self._worker: threading.Thread | None = None

    def ready(self, physics: VRPhysics) -> FootholdGraph | None:
        """
        The graph of `physics` if it is built; otherwise `None`, and it is
        built in the worker thread. Never blocks on a build.
        """
        with self._lock:
            graph = self._graphs.get(physics)
            if graph is not None:
                self._graphs.move_to_end(physics)
                return graph
            failure = self._failed.get(physics)
            if failure is not None and self._clock() < failure.retry_at:
                return None
            if physics != self._building:
                if self._wanted is not None and self._wanted != physics:
                    # A `graph()` waiting on the stats replaced builds them itself.
                    self._built.notify_all()
                self._wanted = physics
                self._start_worker()
            return None

    def prepare(self, physics: VRPhysics) -> None:
        """Starts building the graph of `physics`, unless it is built or building."""
        self.ready(physics)

    def is_building(self) -> bool:
        """Whether the worker is building a graph, or has one left to build."""
        with self._lock:
            return self._building is not None or self._wanted is not None

    def graph(self, physics: VRPhysics) -> FootholdGraph:
        """
        The graph of `physics`, built now if it isn't, or waited for if the
        worker is building it. Blocks: for offline callers only. A failed
        build is tried again now, whatever the back-off.

        :raises Exception: Whatever its build raised.
        """
        with self._lock:
            while physics == self._building or physics == self._wanted:
                self._built.wait()
            graph = self._graphs.get(physics)
            if graph is not None:
                self._graphs.move_to_end(physics)
                return graph
        graph = self._build(physics)
        with self._lock:
            self._failed.pop(physics, None)
            return self._store(physics, graph)

    # --- the worker -------------------------------------------------------------

    def _start_worker(self) -> None:
        """Starts the worker unless it runs. Called with the lock held."""
        if self._worker is not None:
            return
        self._worker = threading.Thread(
            target=self._work,
            name=f"foothold-graphs-{self.world_map.id}",
            daemon=True,
        )
        self._worker.start()

    def _work(self) -> None:
        # Every way out of the lock notifies: a `graph()` caller waits while its
        # physics are `_wanted`, and must be woken when they no longer are.
        while True:
            with self._lock:
                physics = self._wanted
                self._wanted = None
                if physics is None:
                    self._worker = None
                    self._built.notify_all()
                    return
                if physics in self._graphs:
                    self._built.notify_all()
                    continue
                self._building = physics
            try:
                graph: FootholdGraph | None = self._build(physics)
            except Exception:
                graph = None
                attempts, delay = self._record_failure(physics)
                logger.exception(
                    "Building the foothold graph of map %d failed (attempt %d, "
                    "teleport %s): no Path is planned with these stats until a "
                    "build succeeds. Next try in %.0f s. Physics: %s",
                    self.world_map.id,
                    attempts,
                    self.teleport,
                    delay,
                    physics,
                )
            with self._lock:
                if graph is not None:
                    self._failed.pop(physics, None)
                    self._store(physics, graph)
                self._building = None
                self._built.notify_all()

    def _record_failure(self, physics: VRPhysics) -> tuple[int, float]:
        """
        Records a failed build of `physics`, and when to try it again.

        :returns: How many builds of `physics` have failed in a row, and the
            seconds until the next try.
        """
        with self._lock:
            previous = self._failed.get(physics)
            attempts = 1 if previous is None else previous.attempts + 1
            delay = min(self.RETRY_AFTER * 2 ** (attempts - 1), self.RETRY_MAX)
            self._failed[physics] = _Failure(attempts, self._clock() + delay)
        return attempts, delay

    def _build(self, physics: VRPhysics) -> FootholdGraph:
        logger.info("Building the foothold graph of map %d.", self.world_map.id)
        return FootholdGraph.build(self.world_map, physics, teleport=self.teleport)

    def _store(self, physics: VRPhysics, graph: FootholdGraph) -> FootholdGraph:
        """Keeps `graph`, dropping the least recently asked. Lock held."""
        kept = self._graphs.setdefault(physics, graph)
        self._graphs.move_to_end(physics)
        while len(self._graphs) > self.LRU:
            self._graphs.popitem(last=False)
        return kept
