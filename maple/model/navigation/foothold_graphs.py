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
"""

import logging
import threading
from collections import OrderedDict

from botting import PARENT_LOG
from maple.model.mechanics.physics import VRPhysics
from maple.model.world import WorldMap

from .foothold_graph import FootholdGraph

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class FootholdGraphs:
    """
    A map's foothold graphs, one per `VRPhysics`, built in a worker thread.

    :ivar world_map: The map the graphs are built on.
    :ivar teleport: Whether the graphs hold teleport moves.
    """

    #: How many graphs are kept, the most recently asked for first.
    LRU = 2

    def __init__(self, world_map: WorldMap, *, teleport: bool) -> None:
        self.world_map = world_map
        self.teleport = teleport
        self._lock = threading.Lock()
        self._built = threading.Condition(self._lock)
        self._graphs: OrderedDict[VRPhysics, FootholdGraph] = OrderedDict()
        # The physics asked for last and not built yet, which the worker builds
        # next; and the physics it is building now.
        self._wanted: VRPhysics | None = None
        self._building: VRPhysics | None = None
        # Physics whose build raised: not tried again, so a bug in the build
        # logs once instead of every cycle.
        self._failed: dict[VRPhysics, BaseException] = {}
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
            if physics not in self._failed and physics != self._building:
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
        worker is building it. Blocks: for offline callers only.

        :raises Exception: Whatever its build raised.
        """
        with self._lock:
            while physics == self._building or physics == self._wanted:
                self._built.wait()
            graph = self._graphs.get(physics)
            if graph is not None:
                self._graphs.move_to_end(physics)
                return graph
            if physics in self._failed:
                raise self._failed[physics]
        graph = self._build(physics)
        with self._lock:
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
        while True:
            with self._lock:
                physics = self._wanted
                self._wanted = None
                if physics is None:
                    self._worker = None
                    return
                if physics in self._graphs:
                    continue
                self._building = physics
            try:
                graph: FootholdGraph | None = self._build(physics)
            except Exception as error:
                logger.exception(
                    "Building the foothold graph of map %d failed: no Path is "
                    "planned with these stats.",
                    self.world_map.id,
                )
                graph = None
                failure: BaseException | None = error
            else:
                failure = None
            with self._lock:
                if graph is not None:
                    self._store(physics, graph)
                elif failure is not None:
                    self._failed[physics] = failure
                self._building = None
                self._built.notify_all()

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
