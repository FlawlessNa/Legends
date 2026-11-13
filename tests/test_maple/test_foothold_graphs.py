"""
`FootholdGraphs` (#430): a map's foothold graphs, built in a worker thread so a
build never stalls the decision loop.

The builds are stand-ins that wait on an `Event`, so a test holds a build open
for as long as it needs, and counts what was built. One test builds a real
graph, on a movement lab Fixture map.
"""

import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import replace

import pytest

from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraph, FootholdGraphs, foothold_graphs
from maple.model.world import WorldMap
from tests.test_maple.movement_lab import corpus

PHYSICS = corpus.LAB_PHYSICS
BUFFED = replace(PHYSICS, jump_speed=1.2 * PHYSICS.jump_speed)
FASTER = replace(PHYSICS, walk_speed=1.4 * PHYSICS.walk_speed)
WAIT = 5.0  # seconds: far longer than any of these steps takes


def _world() -> WorldMap:
    return corpus.world_map(
        next(e for e in corpus.FIXTURE_MAPS if e.name == "jump_gap")
    )


class _Builds:
    """Stands in for `FootholdGraph.build`: each build waits for its gate."""

    def __init__(self) -> None:
        self.started: list[VRPhysics] = []
        self.threads: list[str] = []
        self.gates: dict[VRPhysics, threading.Event] = {}
        self.fail: set[VRPhysics] = set()
        self._started = threading.Condition()

    def gate(self, physics: VRPhysics) -> threading.Event:
        return self.gates.setdefault(physics, threading.Event())

    def build(self, world_map: object, physics: VRPhysics, *, teleport: bool) -> object:
        with self._started:
            self.started.append(physics)
            self.threads.append(threading.current_thread().name)
            self._started.notify_all()
        assert self.gate(physics).wait(WAIT), "the test never opened this build"
        if physics in self.fail:
            raise RuntimeError("the build broke")
        return ("graph", physics)

    def wait_started(self, physics: VRPhysics) -> None:
        with self._started:
            assert self._started.wait_for(lambda: physics in self.started, WAIT)


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Builds]:
    stand_in = _Builds()
    monkeypatch.setattr(foothold_graphs.FootholdGraph, "build", stand_in.build)
    yield stand_in
    for gate in stand_in.gates.values():  # no worker left waiting on a test
        gate.set()


def _settle(graphs: FootholdGraphs) -> None:
    deadline = time.monotonic() + WAIT
    while graphs.is_building():
        assert time.monotonic() < deadline, "the worker never finished"
        time.sleep(0.001)


def test_asking_for_a_graph_never_waits_for_its_build(builds: _Builds) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)

    asked = time.perf_counter()
    first = graphs.ready(PHYSICS)
    took = time.perf_counter() - asked

    builds.wait_started(PHYSICS)
    assert first is None
    assert took < 0.5  # the build is held open for up to WAIT
    assert graphs.ready(PHYSICS) is None  # still building: asked again, still None
    assert builds.started == [PHYSICS]  # and not started twice
    builds.gate(PHYSICS).set()
    _settle(graphs)
    assert graphs.ready(PHYSICS) == ("graph", PHYSICS)


def test_the_build_runs_off_the_asking_thread(builds: _Builds) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    builds.gate(PHYSICS).set()

    graphs.prepare(PHYSICS)
    _settle(graphs)

    assert builds.threads == [f"foothold-graphs-{_world().id}"]
    assert builds.threads[0] != threading.current_thread().name


def test_only_the_last_stats_asked_during_a_build_are_built_next(
    builds: _Builds,
) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    graphs.prepare(PHYSICS)
    builds.wait_started(PHYSICS)

    graphs.prepare(BUFFED)  # the stats changed twice while PHYSICS built
    graphs.prepare(FASTER)
    builds.gate(PHYSICS).set()
    builds.gate(FASTER).set()
    _settle(graphs)

    assert builds.started == [PHYSICS, FASTER]
    assert graphs.ready(FASTER) == ("graph", FASTER)


def test_stats_that_flip_back_cost_no_build(builds: _Builds) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    for physics in (PHYSICS, BUFFED):
        builds.gate(physics).set()
        graphs.prepare(physics)
        _settle(graphs)

    assert graphs.ready(PHYSICS) == ("graph", PHYSICS)  # the buff wore off
    assert graphs.ready(BUFFED) == ("graph", BUFFED)  # and came back
    assert builds.started == [PHYSICS, BUFFED]


def test_the_least_recently_asked_graph_is_dropped(builds: _Builds) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    for physics in (PHYSICS, BUFFED, FASTER):
        builds.gate(physics).set()
        graphs.prepare(physics)
        _settle(graphs)

    assert graphs.ready(PHYSICS) is None  # dropped: built again
    _settle(graphs)
    assert builds.started == [PHYSICS, BUFFED, FASTER, PHYSICS]


def test_a_build_that_raises_is_logged_once_and_not_retried(
    builds: _Builds, caplog: pytest.LogCaptureFixture
) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    builds.fail.add(PHYSICS)
    builds.gate(PHYSICS).set()

    with caplog.at_level(logging.ERROR):
        graphs.prepare(PHYSICS)
        _settle(graphs)
        assert graphs.ready(PHYSICS) is None
        _settle(graphs)

    assert builds.started == [PHYSICS]
    assert len([r for r in caplog.records if "failed" in r.getMessage()]) == 1
    with pytest.raises(RuntimeError, match="the build broke"):
        graphs.graph(PHYSICS)


def test_the_blocking_graph_waits_for_the_build_under_way(builds: _Builds) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    graphs.prepare(PHYSICS)
    builds.wait_started(PHYSICS)
    threading.Timer(0.05, builds.gate(PHYSICS).set).start()

    assert graphs.graph(PHYSICS) == ("graph", PHYSICS)
    assert builds.started == [PHYSICS]


def test_the_blocking_graph_builds_on_the_caller_when_nothing_builds_it(
    builds: _Builds,
) -> None:
    graphs = FootholdGraphs(_world(), teleport=False)
    builds.gate(PHYSICS).set()

    assert graphs.graph(PHYSICS) == ("graph", PHYSICS)
    assert graphs.graph(PHYSICS) is graphs.ready(PHYSICS)
    assert not graphs.is_building()


def test_a_real_graph_is_built_in_the_worker() -> None:
    graphs = FootholdGraphs(_world(), teleport=False)

    graphs.prepare(PHYSICS)
    _settle(graphs)

    graph = graphs.ready(PHYSICS)
    assert isinstance(graph, FootholdGraph)
    assert graph.path((100.0, 0.0), (600.0, 0.0)) is not None
