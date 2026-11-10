"""
`PositionFusion` on synthetic readings: a camera reader, a character finder
and a minimap reading made up for each case, so each rule of the fusion is
tried alone. The frame set's frames are `test_position_fusion_frames.py`'s.
"""

import numpy as np
import pytest

from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from game_data.catalogue import Bounds, Minimap
from maple.model.world import MinimapTransform, WorldMap
from maple.screen.minimap import MinimapState, MinimapView, virtual_feet
from maple.screen.position import (
    WINDOW,
    Camera,
    CharacterSighting,
    PositionFusion,
    PositionSource,
    VirtualPosition,
)

TRANSFORM = MinimapTransform(centre=(1000, 2000), mag=4)
MARKER = (100, 140)
"""The marker's canvas pixel: the feet's is (100, 146), whose top-left is
(600, 336) virtual, so the minimap's feet position is (608, 344)."""
FEET = (608, 344)
CAMERA = Camera(200, 50, 0.9, 3.0, (1366, 768))
AT = 5.0


def screen(size: tuple[int, int] = (1366, 768)) -> Frame:
    width, height = size
    return Frame(np.zeros((height, width, 3), np.uint8), size, AT, True, True)


def minimap(
    marker: Reading[tuple[int, int]] | None = None,
) -> Reading[MinimapView]:
    view = MinimapView(
        MinimapState.EXPANDED,
        Box(left=10, right=180, top=40, bottom=150),
        Box(left=0, right=190, top=0, bottom=160),
        marker or Reading.read(MARKER, AT),
    )
    return Reading.read(view, AT)


class Cameras:
    """Answers `reading`, and remembers the seeds it was given."""

    def __init__(self, reading: Reading[Camera]) -> None:
        self.reading = reading
        self.seeds: list[Camera | None] = []

    def read(self, frame: Frame, seed: Camera | None = None) -> Reading[Camera]:
        self.seeds.append(seed)
        return self.reading


class Finder:
    """Answers `reading`, remembers where it was told ours is, and says it can
    tell ours apart when `knows`."""

    def __init__(
        self, reading: Reading[list[CharacterSighting]], knows: bool = False
    ) -> None:
        self.reading = reading
        self.knows = knows
        self.taught: list[tuple[float, float]] = []

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        return self.reading

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        self.taught.append(near)
        return self.knows


def seen(*feet: tuple[float, float], own: int | None = None) -> Finder:
    """Characters at these virtual feet, with `CAMERA` at 1:1; the one at
    index `own` marked ours, by a finder that can tell ours apart when `own`
    is given."""
    sightings = [
        CharacterSighting((x - CAMERA.x, y - CAMERA.y), "name tag", 0.9, i == own)
        for i, (x, y) in enumerate(feet)
    ]
    return Finder(Reading.read(sightings, AT), knows=own is not None)


def fusion(
    finder: Finder, cameras: Cameras | None = None
) -> tuple[PositionFusion, Cameras]:
    cameras = cameras or Cameras(Reading.read(CAMERA, AT))
    return PositionFusion(TRANSFORM, lambda: cameras, finder), cameras


def placed(reading: Reading[VirtualPosition]) -> tuple[float, float, str]:
    value = reading.value
    assert value is not None, reading.detail
    return value.x, value.y, value.source


def test_the_minimaps_feet_position_is_the_middle_of_virtual_feets_pixel() -> None:
    """#311's conversion, through the map's transform, gives the canvas
    pixel's top-left: the middle is half a canvas pixel on."""
    as_311 = virtual_feet(MARKER, Minimap(1000, 2000, 4, 0, 0))
    result = fusion(seen())[0].read(screen(), minimap())

    assert (as_311[0] + 8, as_311[1] + 8) == FEET
    assert result.minimap == FEET


def test_one_character_by_the_minimaps_is_ours_to_the_pixel() -> None:
    result = fusion(seen((608.5, 340)))[0].read(screen(), minimap())

    assert placed(result.position) == (608.5, 340, PositionSource.FUSED)
    assert result.near == 1
    assert not result.by_tag


def test_feet_are_scaled_to_the_play_areas_render_size() -> None:
    """At 1920x1200 the play area is drawn 1228x768 and upscaled."""
    camera = Camera(200, 50, 0.6, 2.0, (1228, 768))
    sx, sy = 1920 / 1228, 1200 / 768
    feet = ((605 - 200) * sx, (340 - 50) * sy)
    finder = Finder(Reading.read([CharacterSighting(feet, "name tag", 0.9)], AT))
    result = fusion(finder, Cameras(Reading.read(camera, AT)))[0].read(
        screen((1920, 1200)), minimap()
    )

    x, y, source = placed(result.position)
    assert (x, y) == pytest.approx((605, 340))
    assert source is PositionSource.FUSED


@pytest.mark.parametrize(
    "marker",
    [
        Reading.covered(AT, "under the cursor"),
        Reading.unsure(AT, "canvas not found"),
    ],
)
def test_without_the_minimaps_position_the_position_is_unsure(
    marker: Reading[tuple[int, int]],
) -> None:
    """Even with a character on screen: nothing would check it."""
    result = fusion(seen((605, 340), own=0))[0].read(screen(), minimap(marker))

    assert result.position.status is Status.UNSURE
    assert "minimap position" in result.position.detail


def test_without_the_minimap_the_position_is_unsure() -> None:
    result = fusion(seen((605, 340)))[0].read(screen(), Reading.absent(AT, "not found"))

    assert result.position.status is Status.UNSURE
    assert result.position.detail == "minimap absent: not found"


def test_without_a_camera_the_minimaps_position_is_used_coarse() -> None:
    finder = seen((605, 340))
    cameras = Cameras(Reading.unsure(AT, "a dialog over the play area"))
    result = fusion(finder, cameras)[0].read(screen(), minimap())

    assert placed(result.position) == (*FEET, PositionSource.COARSE)
    assert "a dialog over the play area" in result.position.detail
    assert finder.taught == []


def test_without_characters_read_the_minimaps_position_is_used_coarse() -> None:
    finder = Finder(Reading.unsure(AT, "no tag scale"))
    result = fusion(finder)[0].read(screen(), minimap())

    assert placed(result.position) == (*FEET, PositionSource.COARSE)
    assert result.camera == CAMERA


def test_a_character_away_from_the_minimaps_is_never_ours() -> None:
    """Another player across the screen, ours hidden: the minimap, coarse."""
    result = fusion(seen((900, 336)))[0].read(screen(), minimap())

    assert placed(result.position) == (*FEET, PositionSource.COARSE)
    assert result.near == 0
    assert len(result.sightings) == 1


@pytest.mark.parametrize("dx", [-WINDOW, WINDOW])
def test_the_window_is_inclusive_but_the_cross_check_still_applies(dx: int) -> None:
    """A character at the window's edge is a candidate, and it puts the
    marker 2 canvas px off to the right (or 2 left): the reads disagree."""
    result = fusion(seen((FEET[0] + dx, 336)))[0].read(screen(), minimap())

    assert result.near == 1
    assert result.position.status is Status.UNSURE
    assert "disagree" in result.position.detail


@pytest.mark.parametrize("dx", [-WINDOW - 1, WINDOW + 1])
def test_a_character_past_the_window_is_not_a_candidate(dx: int) -> None:
    result = fusion(seen((FEET[0] + dx, 336)))[0].read(screen(), minimap())

    assert result.near == 0
    assert placed(result.position)[2] is PositionSource.COARSE


@pytest.mark.parametrize(
    ("feet", "fused"),
    [
        ((584, 336), True),  # one cell left: agrees
        ((631.9, 367.9), True),  # one cell right, one down
        ((583.9, 336), False),  # two cells left
        ((600, 368), False),  # two cells down
    ],
)
def test_the_reads_agree_within_one_canvas_pixel(
    feet: tuple[float, float], fused: bool
) -> None:
    result = fusion(seen(feet))[0].read(screen(), minimap())

    assert (result.position.status is Status.READ) is fused, result.position.detail


def test_of_several_by_the_minimaps_our_tag_chooses() -> None:
    result = fusion(seen((598, 336), (612, 336), own=1))[0].read(screen(), minimap())

    assert placed(result.position) == (612, 336, PositionSource.FUSED)
    assert result.by_tag
    assert result.near == 2


def test_of_several_by_the_minimaps_with_no_telling_the_position_is_unsure() -> None:
    result = fusion(seen((598, 336), (612, 336)))[0].read(screen(), minimap())

    assert result.position.status is Status.UNSURE
    assert "2 characters" in result.position.detail
    assert result.minimap == FEET


def test_once_ours_can_be_told_apart_one_not_ours_by_the_minimaps_is_not_ours() -> None:
    """A pet's tag, a sword or a chat balloon next to us, our tag hidden: the
    finder would have marked ours, so the minimap's, coarse."""
    finder = seen((605, 340))
    finder.knows = True
    result = fusion(finder)[0].read(screen(), minimap())

    assert placed(result.position) == (*FEET, PositionSource.COARSE)
    assert "with our tag" in result.position.detail
    assert result.near == 1


def test_our_tag_away_from_the_minimaps_is_reported_not_followed() -> None:
    """A tag learned wrong can't move the position off the minimap's."""
    result = fusion(seen((605, 340), (900, 340), own=1))[0].read(screen(), minimap())

    assert placed(result.position) == (*FEET, PositionSource.COARSE)
    assert result.own_elsewhere


def test_a_tag_marked_ours_elsewhere_is_reported_even_before_it_tells_ours_apart() -> (
    None
):
    finder = seen((605, 340), (900, 340), own=1)
    finder.knows = False
    result = fusion(finder)[0].read(screen(), minimap())

    assert placed(result.position) == (605, 340, PositionSource.FUSED)
    assert result.own_elsewhere
    assert not result.by_tag


def test_the_last_camera_seeds_the_next_read() -> None:
    reader, cameras = fusion(seen((605, 340)))
    reader.read(screen(), minimap())
    reader.read(screen(), minimap())

    assert cameras.seeds == [None, CAMERA]


def test_the_finder_is_taught_where_the_minimap_puts_us_in_client_px() -> None:
    """The middle of the feet's canvas pixel, on screen."""
    camera = Camera(200, 50, 0.6, 2.0, (1366, 768))
    finder = seen()
    fusion(finder, Cameras(Reading.read(camera, AT)))[0].read(
        screen((1920, 1080)), minimap()
    )

    ((x, y),) = finder.taught
    assert (x, y) == pytest.approx(((608 - 200) * 1920 / 1366, (344 - 50) * 1080 / 768))


def test_the_camera_reader_is_made_on_the_first_read_only() -> None:
    made: list[Cameras] = []

    def make() -> Cameras:
        made.append(Cameras(Reading.read(CAMERA, AT)))
        return made[-1]

    reader = PositionFusion(TRANSFORM, make, seen((605, 340)))
    assert made == []
    reader.read(screen(), minimap())
    reader.read(screen(), minimap())
    assert len(made) == 1


def test_a_map_without_a_minimap_has_no_fusion() -> None:
    world_map = WorldMap(1, None, None, Bounds(0, 0, 10, 10), None, (), (), (), ())

    with pytest.raises(ValueError, match="no minimap"):
        PositionFusion.for_map(world_map)
