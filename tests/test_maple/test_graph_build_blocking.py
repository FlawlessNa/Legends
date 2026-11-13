"""
How long the decision loop is blocked while a foothold graph builds, on the
real maps (#430): `toolkit.graph_build_blocking`, run as a test.

`lab`: each figure is a reading of this machine at this moment, against
whatever else runs on it, so it measures rather than gates. `client_files`:
the maps come from the game data store.

    pytest -m "lab and client_files" tests/test_maple/test_graph_build_blocking.py
        -o log_cli=true --log-cli-level=INFO
"""

import logging

import pytest

from maple.model.mechanics.physics import game_physics
from maple.model.world import WorldMap
from toolkit.graph_build_blocking import HEADER, measure

pytestmark = [pytest.mark.lab, pytest.mark.client_files]

logger = logging.getLogger(__name__)

#: "No single cycle blocks for more than a small fraction of a second" (#430).
#: Measured at 5 to 12 ms on the maintainer's machine with two other agents
#: running; a tenth of a second leaves room for a loaded machine.
SMALL_FRACTION = 0.1


@pytest.mark.parametrize("teleport", [False, True], ids=["walking", "teleport"])
@pytest.mark.parametrize("name", ["Victoria Road: Ellinia", "Damp Forest"])
def test_a_graph_builds_without_blocking_the_loop(name: str, teleport: bool) -> None:
    world_map = WorldMap.load(name)
    values = game_physics()

    before = measure(world_map, values, teleport=teleport, mode="before")
    after = measure(world_map, values, teleport=teleport, mode="after")
    logger.info("\n%s\n%s\n%s", HEADER, before.row(), after.row())

    assert len(after.builds) == 2  # the profile's stats, then the buff's
    assert after.longest_block < SMALL_FRACTION
    assert after.longest_step < SMALL_FRACTION
