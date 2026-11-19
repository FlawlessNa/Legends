"""
The other players, as the minimap marks them (#571, spec section 4).

`OTHER_PLAYERS` is where the minimap draws the `another` markers, in virtual px,
and the part of the map the minimap shows. A marker has no identity: these are
points, not players one can follow from read to read. A marker is placed by its
sprite's centre (`markers_in_virtual`), good to about one canvas px, plus an
offset from that player's feet that is not measured yet.

`friend`, `party`, `partymaster`, `guild` and `guildmaster` markers are not
other players here: only `another` is read.

**What it costs.** Only `another` is matched, about 2 ms a read, at most once a
second, and only when something reads the key. Registering it reads nothing.
"""

from dataclasses import dataclass

from botting.core import Key, Provider
from botting.screen import Reading, Status
from botting.utilities import Box
from maple.model.world import WorldMap
from maple.screen.minimap import MinimapView, markers_in_virtual, shown_in_virtual

from .client import FRAME
from .map import WORLD_MAP
from .screen_readers import MINIMAP_READER

type Point = tuple[float, float]

#: The marker kind that is another player.
ANOTHER = "another"


@dataclass(frozen=True, slots=True)
class OtherPlayers:
    """
    The other players the minimap marks, read once.

    :ivar positions: Where each `another` marker is drawn, in virtual px.
    :ivar visible: The part of the map the minimap's map area shows, in virtual
        px; `None` when it is not known. A player outside it is not seen.
    """

    positions: tuple[Point, ...]
    visible: Box | None


class OtherPlayersProvider(Provider):
    """
    Serves `OTHER_PLAYERS`, read from the current frame's minimap with the
    `another` markers asked for, and nothing else.

    `UNSURE` whenever the minimap does not read the character's own position as
    sure or covered (minimised, its canvas not found, the frame unusable), or the
    map has no minimap: its markers then mean nothing. A covered own marker
    still gives the others: one drawn over it is likely another player.
    """

    needs = (FRAME, MINIMAP_READER, WORLD_MAP)

    #: Seconds a reading is served before a read refreshes it.
    REFRESH = 1.0

    def setup(self) -> None:
        # No read here: nothing reads it unless the rotation is `hunting_area`.
        self.register(
            OTHER_PLAYERS,
            self._read,
            threshold=self.REFRESH,
            initial_value=Reading.unsure(0.0, "not read yet"),
        )

    def _read(self) -> Reading[OtherPlayers]:
        world_map = self.read(WORLD_MAP)
        reader = self.read(MINIMAP_READER)
        if world_map is None or world_map.minimap is None or reader is None:
            return Reading.unsure(0.0, "no minimap is read on this map")
        frame = self.read(FRAME)
        return other_players(reader.read(frame, markers=(ANOTHER,)), world_map)


#: The other players' markers, in virtual px, read at most once a second.
OTHER_PLAYERS: Key[Reading[OtherPlayers]] = Key("other_players", OtherPlayersProvider)


def other_players(
    minimap: Reading[MinimapView], world_map: WorldMap
) -> Reading[OtherPlayers]:
    """
    The `another` markers of a minimap reading, in virtual px
    (`MinimapTransform.to_virtual`); `UNSURE` when the minimap places no
    position at all, or the map has no minimap.
    """
    transform = world_map.minimap
    view = minimap.value
    if view is None or transform is None:
        return Reading.unsure(minimap.frame_time, minimap.detail or "no minimap read")
    own = view.self_position
    if own.status not in (Status.READ, Status.COVERED):
        return Reading.unsure(minimap.frame_time, own.detail or "no position read")
    positions = markers_in_virtual(view.markers.get(ANOTHER, ()), transform)
    visible = None if view.shown is None else shown_in_virtual(view.shown, transform)
    return Reading.read(
        OtherPlayers(tuple((float(x), float(y)) for x, y in positions), visible),
        minimap.frame_time,
    )
