"""
`OTHER_PLAYERS` (#578): the `another` markers of the minimap, in virtual px.

No game client: the minimap reader is a stand-in that returns the view the test
sets and records the markers each read asks for, and the Bot-level Providers are
built as `MapleBot.child_init` builds them (`serving.serve`).
"""

from collections.abc import Iterable
from dataclasses import replace

import pytest

from botting.core import BotData
from botting.screen import Reading, Status
from botting.utilities import Box
from maple.decision_makers.providers import (
    OTHER_PLAYERS,
    MapProvider,
    OtherPlayers,
    OtherPlayersProvider,
)
from maple.model.world import MinimapTransform, WorldMap
from maple.screen.minimap import MinimapState, MinimapView
from tests.test_maple.serving import Served, serve
from tests.test_maple.test_hunting_area import fixture_map

#: The Fixture map, with a canvas px 16 virtual px and the canvas's top left at
#: virtual (-500, -1500).
TRANSFORM = MinimapTransform((500, 1500), 4)
WORLD = replace(fixture_map(), minimap=TRANSFORM)
#: Where the markers are drawn on the canvas.
ANOTHER = ((40, 57), (100, 90))
FRIEND = ((60, 60),)


def view(
    own: Reading[tuple[int, int]] | None = None,
    markers: dict[str, tuple[tuple[int, int], ...]] | None = None,
) -> MinimapView:
    """An expanded minimap that shows the canvas from (0, 37) to (80, 97)."""
    return MinimapView(
        state=MinimapState.EXPANDED,
        map_area=Box(left=10, right=90, top=30, bottom=90),
        bounds=Box(left=0, right=100, top=0, bottom=100),
        self_position=own or Reading.read((50, 60), 1.0),
        markers={"another": ANOTHER, "friend": FRIEND} if markers is None else markers,
        shown=Box(left=0, right=80, top=37, bottom=97),
    )


class Reader:
    """A minimap reader: returns `reading`, and records the markers asked for."""

    def __init__(self, reading: Reading[MinimapView]) -> None:
        self.reading = reading
        self.asked: list[tuple[str, ...]] = []

    def read(self, frame: object, markers: Iterable[str] = ()) -> Reading[MinimapView]:
        self.asked.append(tuple(markers))
        return self.reading


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def built(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    world: WorldMap = WORLD,
    clock: Clock | None = None,
) -> Served:
    served = serve(
        monkeypatch,
        data=BotData("Bot", clock=clock or Clock()),
        frames=lambda: object(),
        minimap=reader,
    )
    served.providers.add(MapProvider, map_id=world.id, world_map=world)
    served.providers.build([OtherPlayersProvider])
    return served


def test_building_the_provider_reads_no_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Reader(Reading.read(view(), 1.0))
    served = serve(monkeypatch, frames=lambda: object(), minimap=reader)
    served.providers.add(MapProvider, map_id=WORLD.id, world_map=WORLD)
    grabs = served.client.grabs

    served.providers.build([OtherPlayersProvider])

    assert served.client.grabs == grabs
    assert reader.asked == []
    # Its initial value, unread: `peek` and `read` would not show an unsure one.
    initial = served.data._managed[OTHER_PLAYERS.name].value  # pyright: ignore[reportPrivateUsage]
    assert initial.status is Status.UNSURE


def test_it_asks_the_reader_for_the_another_markers_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = Reader(Reading.read(view(), 1.0))
    served = built(monkeypatch, reader)

    served.data.update_attribute(OTHER_PLAYERS.name)

    assert reader.asked == [("another",)]


def test_the_markers_are_converted_with_the_minimaps_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served = built(monkeypatch, Reader(Reading.read(view(), 1.0)))

    served.data.update_attribute(OTHER_PLAYERS.name)
    reading = served.data.read(OTHER_PLAYERS)

    assert reading.value == OtherPlayers(
        positions=tuple(TRANSFORM.to_virtual(p) for p in ANOTHER),
        visible=Box(left=-500, right=780, top=-908, bottom=52),
    )


def test_a_friend_is_not_another_player(monkeypatch: pytest.MonkeyPatch) -> None:
    served = built(
        monkeypatch, Reader(Reading.read(view(markers={"friend": FRIEND}), 1.0))
    )

    served.data.update_attribute(OTHER_PLAYERS.name)

    assert served.data.read(OTHER_PLAYERS).value == OtherPlayers(
        (), Box(left=-500, right=780, top=-908, bottom=52)
    )


@pytest.mark.parametrize(
    "minimap",
    [
        Reading.read(view(own=Reading.unsure(1.0, "canvas not found")), 1.0),
        Reading.unsure(1.0, "minimap not found"),
    ],
    ids=["position unsure", "minimap unsure"],
)
def test_it_is_unsure_when_the_minimaps_position_is(
    monkeypatch: pytest.MonkeyPatch, minimap: Reading[MinimapView]
) -> None:
    served = built(monkeypatch, Reader(minimap))

    served.data.update_attribute(OTHER_PLAYERS.name)

    assert served.data.read(OTHER_PLAYERS).status is Status.UNSURE


def test_a_covered_own_marker_still_gives_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another marker drawn over ours is most likely another player."""
    covered = view(own=Reading.covered(1.0, "under another marker"))
    served = built(monkeypatch, Reader(Reading.read(covered, 1.0)))

    served.data.update_attribute(OTHER_PLAYERS.name)

    reading = served.data.read(OTHER_PLAYERS)
    assert reading.value is not None
    assert len(reading.value.positions) == len(ANOTHER)


def test_a_map_with_no_minimap_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Reader(Reading.read(view(), 1.0))
    served = built(monkeypatch, reader, world=fixture_map())

    served.data.update_attribute(OTHER_PLAYERS.name)

    assert served.data.read(OTHER_PLAYERS).status is Status.UNSURE
    assert reader.asked == []


def test_it_is_read_at_most_once_a_second(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    reader = Reader(Reading.read(view(), 1.0))
    served = built(monkeypatch, reader, clock=clock)

    for now in (0.0, 0.5, 1.0, 1.5, 2.0):
        clock.now = now
        served.data.read(OTHER_PLAYERS)

    # Never read before, so read at 0 s; then again once more than a second has
    # passed, at 1.5 s, and not at 2 s.
    assert len(reader.asked) == 2
