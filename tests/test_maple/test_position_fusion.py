"""
`PositionFusion` on synthetic readings: a camera reader, a character finder
and a minimap reading made up for each case, so each rule of the fusion is
tried alone. The frame set's frames are `test_position_fusion_frames.py`'s.
"""

from collections.abc import Callable

import numpy as np
import pytest
from numpy.typing import NDArray

from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from game_data.catalogue import Bounds, Foothold, LayerFrame, MapLayer, Minimap
from maple.model.world import FrontArt, MinimapTransform, Platform, WorldMap
from maple.screen.minimap import MinimapState, MinimapView, virtual_feet
from maple.screen.position import (
    WINDOW,
    Camera,
    CharacterFinder,
    CharacterSighting,
    NameTagFinder,
    PositionFusion,
    PositionSource,
    VirtualPosition,
)
from tests.test_maple.test_screen_characters import (
    OURS,
    art_over,
    blank,
    draw_tag,
    feet_over,
    text_box,
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
        self.hidden: CharacterSighting | None = None
        """What `find_own_hidden` answers."""
        self.asked: list[tuple[tuple[float, float], Covered]] = []

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        return self.reading

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        self.taught.append(near)
        return self.knows

    def find_own_hidden(
        self, frame: Frame, near: tuple[float, float], covered: Covered
    ) -> CharacterSighting | None:
        self.asked.append((near, covered))
        return self.hidden


type Covered = Callable[[tuple[int, int, int, int]], NDArray[np.bool_]]


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


# --- the camera of the last read (#398) ----------------------------------------


def test_the_last_reads_camera_places_what_was_found_on_its_frame() -> None:
    reader, _ = fusion(seen((605, 340)))
    assert reader.camera is None  # before the first read

    reader.read(screen(), minimap())

    assert reader.camera == CAMERA
    assert CAMERA.to_virtual((405.0, 290.0), (1366, 768)) == (605.0, 340.0)


def test_a_read_that_matched_no_camera_has_none_never_an_older_one() -> None:
    cameras = Cameras(Reading.read(CAMERA, AT))
    reader, _ = fusion(seen((605, 340)), cameras)
    reader.read(screen(), minimap())

    cameras.reading = Reading.unsure(AT, "mid-resize")
    reader.read(screen(), minimap())

    assert reader.camera is None


def test_a_camera_places_client_px_scaled_to_the_play_area() -> None:
    """1366x768 drawn at 1920x1080: 1920 client px are 1366 virtual px wide."""
    camera = Camera(200, 50, 0.9, 3.0, (1366, 768))

    x, y = camera.to_virtual((960.0, 540.0), (1920, 1080))

    assert (x, y) == pytest.approx((200 + 683, 50 + 384))


# --- our tag behind the map's art (#517) -------------------------------------


def ground(layer: int = 1, y: int = 344) -> WorldMap:
    """A flat platform under `FEET`, on `layer`."""
    platform = Platform(layer, (Foothold("map", layer, 0, 1, 500, y, 700, y, 0, 0),))
    return WorldMap(
        1, None, None, Bounds(0, 0, 2000, 2000), TRANSFORM, (platform,), (), (), ()
    )


def art(*pieces: tuple[int, int, int, int, int]) -> FrontArt:
    """Solid art `(layer, left, top, right, bottom)`, in virtual px."""
    images = {
        f"{n}": np.full((bottom - top, right - left, 4), 255, np.uint8)
        for n, (_, left, top, right, bottom) in enumerate(pieces)
    }
    items = [
        MapLayer(
            "object",
            layer,
            0,
            0,
            left,
            top,
            False,
            "a",
            (LayerFrame(0, f"{n}", 0, 0, None),),
            None,
        )
        for n, (layer, left, top, _, _) in enumerate(pieces)
    ]
    return FrontArt.from_layers(items, images.__getitem__)


def shot(image: NDArray[np.uint8]) -> Frame:
    return Frame(image, (1366, 768), AT, True, True)


def behind(
    finder: CharacterFinder,
    world: WorldMap | None = None,
    front: FrontArt | None = None,
) -> PositionFusion:
    drawn = art() if front is None else front
    return PositionFusion(
        TRANSFORM,
        lambda: Cameras(Reading.read(CAMERA, AT)),
        finder,
        world_map=ground() if world is None else world,
        front_art=lambda: drawn,
    )


def test_ours_partly_behind_the_maps_art_is_ours_by_what_is_seen() -> None:
    """Something else beside us, untagged, and our tag found only where the
    art doesn't hide it: fused there."""
    finder = seen((598, 340))
    finder.knows = True
    finder.hidden = CharacterSighting((406.5, 291), "name tag", 0.9, True)

    result = behind(finder).read(screen(), minimap())

    assert placed(result.position) == (606.5, 341, PositionSource.FUSED)
    assert result.position.detail == "ours by its tag, part of it behind the map's art"
    assert result.by_tag
    assert result.near == 2
    ((near, _),) = finder.asked
    assert near == (FEET[0] - CAMERA.x, FEET[1] - CAMERA.y)


def test_the_art_is_looked_up_on_the_layer_under_us_in_client_px() -> None:
    """Art on layer 2 is in front of a character on the layer-1 platform;
    art on layer 1 isn't. At 1:1 a client pixel is a virtual one, moved by
    the camera."""
    finder = seen()
    finder.knows = True
    front = art((2, 600, 340, 610, 345), (1, 620, 340, 630, 345))

    behind(finder, ground(layer=1), front).read(screen(), minimap())

    ((_, covered),) = finder.asked
    mask = covered((390, 285, 440, 300))  # virtual (590, 335) to (640, 350)
    assert np.argwhere(mask).tolist() == [
        [y, x] for y in range(5, 10) for x in range(10, 20)
    ]


def test_above_1_to_1_the_art_is_scaled_and_grown_by_a_client_pixel() -> None:
    camera = Camera(200, 50, 0.6, 2.0, (1366, 768))
    finder = seen()
    finder.knows = True
    fusion = PositionFusion(
        TRANSFORM,
        lambda: Cameras(Reading.read(camera, AT)),
        finder,
        world_map=ground(),
        front_art=lambda: art((2, 600, 340, 601, 341)),
    )

    fusion.read(screen((1920, 1080)), minimap())

    ((_, covered),) = finder.asked
    ys, xs = np.nonzero(covered((0, 0, 1920, 1000)))
    # The client pixels whose middles fall in virtual (600, 340), and one
    # more on every side.
    middles_x = [c for c in range(1920) if (c + 0.5) * 1366 // 1920 + 200 == 600]
    middles_y = [c for c in range(1000) if (c + 0.5) * 768 // 1080 + 50 == 340]
    assert (xs.min(), xs.max()) == (min(middles_x) - 1, max(middles_x) + 1)
    assert (ys.min(), ys.max()) == (min(middles_y) - 1, max(middles_y) + 1)


def test_a_hidden_tag_is_not_looked_for_where_our_tag_was_found() -> None:
    finder = seen((605, 340), (900, 340), own=1)

    result = behind(finder).read(screen(), minimap())

    assert finder.asked == []
    assert placed(result.position)[2] is PositionSource.COARSE
    assert result.own_elsewhere


def test_a_hidden_tag_is_not_looked_for_before_ours_can_be_told_apart() -> None:
    finder = seen((605, 340))

    behind(finder).read(screen(), minimap())

    assert finder.asked == []


@pytest.mark.parametrize("world", [None, "far"])
def test_without_the_map_or_away_from_its_surfaces_nothing_is_looked_for(
    world: str | None,
) -> None:
    finder = seen((605, 340))
    finder.knows = True
    finder.hidden = CharacterSighting((406.5, 291), "name tag", 0.9, True)
    if world is None:
        fusion = PositionFusion(
            TRANSFORM, lambda: Cameras(Reading.read(CAMERA, AT)), finder
        )
    else:
        fusion = behind(finder, ground(y=600))

    result = fusion.read(screen(), minimap())

    assert finder.asked == []
    assert placed(result.position)[2] is PositionSource.COARSE


def test_a_hidden_tag_still_has_to_agree_with_the_minimap() -> None:
    finder = seen()
    finder.knows = True
    finder.hidden = CharacterSighting((420, 300), "name tag", 0.9, True)  # (620, 350)
    fusion = behind(finder)

    result = fusion.read(screen(), minimap())

    assert placed(result.position) == (620, 350, PositionSource.FUSED)
    finder.hidden = CharacterSighting((300, 290), "name tag", 0.9, True)  # outside
    assert placed(fusion.read(screen(), minimap()).position)[2] is PositionSource.COARSE


def test_with_the_real_finder_ours_under_a_ladder_is_fused() -> None:
    """#517, from the readers' own geometry: our tag learned where the
    minimap puts us, then the top of a ladder (layer 2) drawn over its right
    part while we stand on the layer-1 platform. The whole tag no longer
    scores as ours; what the ladder leaves seen does, at the feet over it."""
    probe = blank()
    draw_tag(probe, OURS, 100, 100)
    offset = feet_over(text_box(probe, 90, 200))
    left, baseline = round(408 - (offset[0] - 100)), round(294 - (offset[1] - 100))
    picture = blank()
    draw_tag(picture, OURS, left, baseline)
    box = text_box(picture, left - 10, left + 110)
    feet = feet_over(box)
    ladder = (
        box[2] - round(0.7 * (box[2] - box[0])),
        box[1] - 5,
        box[2] + 5,
        box[3] + 6,
    )
    covered = picture.copy()
    art_over(covered, ladder)
    front = art(
        (
            2,
            ladder[0] + CAMERA.x,
            ladder[1] + CAMERA.y,
            ladder[2] + CAMERA.x,
            ladder[3] + CAMERA.y,
        )
    )
    finder = NameTagFinder()
    fusion = behind(finder, ground(layer=1), front)
    for _ in range(3):
        assert fusion.read(shot(picture), minimap()).position.status is Status.READ
    assert not any(s.own for s in finder.find(shot(covered)).value or [])

    result = fusion.read(shot(covered), minimap())

    assert placed(result.position) == (
        feet[0] + CAMERA.x,
        feet[1] + CAMERA.y,
        PositionSource.FUSED,
    )
    assert "behind the map's art" in result.position.detail
