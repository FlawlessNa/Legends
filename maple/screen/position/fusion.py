"""
The character's virtual position, from the minimap, the camera and the
characters found (#392, epic #302 Part 2, item 4 and decision N2).

**The minimap first.** The minimap's feet position is the middle of the
canvas pixel the feet are in: the marker's, moved down `FEET_ROWS`, converted
to virtual px as `maple.screen.minimap.virtual_feet` converts it (the pixel's
top-left), plus half a canvas pixel. It is good to about one canvas pixel (16
virtual px): on frame sets v2 and v3, the labelled feet are within 22 virtual
px of it in x and 32 in y, where 39 px of the top-left in y. Without it,
nothing places the character: the position is `UNSURE`, whatever the play area
shows, since nothing would check it.

**Then the play area.** Each character found (`CharacterFinder`) has its feet
in client px. They are scaled to the play area's render size
(`Camera.play_area`) and the camera is added, which puts them in virtual px.
The ones within `WINDOW` of the minimap's feet position, in x and in y, are
kept, and ours is chosen among them:

- Once the finder can tell ours apart (`CharacterFinder.learn_own` says so,
  as `NameTagFinder` can once it has learned our name tag), ours is the one
  it marks ours (`CharacterSighting.own`). Kept sightings it doesn't mark are
  someone else's, or not characters at all: on frame set v3 the name tag
  finder also reads a white sword, a pet's name tag and a chat balloon, each
  next to our character while our own tag is hidden.
- Before then, one kept is ours, and several are `UNSURE`.

**Our tag behind the map's art** (#517). The client draws a character, its
name tag too, with its foothold's layer, and the tiles and objects of every
layer above over it: at the top of Ellinia the ladder's top hides most of our
tag, and the finder no longer finds it. So when the finder can tell ours apart
and found none ours, ours is looked for once more near the minimap's feet
position, on what the art of the layers above ours leaves seen
(`CharacterFinder.find_own_hidden`, the map's `FrontArt`, the layer from
`WorldMap.layer_near`). What it finds is ours like any sighting marked ours:
in the window, and cross-checked.

Our tag counts only inside the window: a tag learned wrong (`NameTagFinder`
never forgets one) can't move the position away from the minimap's, and one
found outside the window is only reported (`Fusion.own_elsewhere`).

**The cross-check.** The character chosen must put the marker within
`AGREE_CELLS` canvas pixel of where the minimap reads it, on each axis; when
it doesn't, the reads disagree and the position is `UNSURE`. Otherwise it is
the position, `fused`.

**The fallback.** When the play area doesn't place our character (the camera
or the finder `UNSURE`, under a dialog say; no character in the window; or
none of ours there, our name tag hidden other than by the map's art), the
minimap's feet position is the position, `coarse`.

Every read returns a `Reading` that is `READ` or `UNSURE`, never a plausible
number (C-NOGUESS); what each read said is kept beside it, in `Fusion`.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Final, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading
from maple.model.world import FrontArt, MinimapTransform, WorldMap
from maple.screen.locator import FrameCheck
from maple.screen.minimap import FEET_ROWS, MinimapView

from .camera import Camera, CameraReader
from .characters import Box, CharacterFinder, CharacterSighting, NameTagFinder

WINDOW: Final = 32
"""Virtual px a character's feet may be from the minimap's feet position, in x
and in y, to be ours (#392): two canvas pixels at `mag` 4, which every
labelled frame of v2 and v3 is within."""

AGREE_CELLS: Final = 1
"""Canvas px the marker may be from where the chosen feet put it, on each axis
(epic #302 Part 2, item 4)."""


class PositionSource(enum.StrEnum):
    """Which reads placed the character."""

    FUSED = "fused"
    """The play area, checked against the minimap: to the virtual px."""
    COARSE = "coarse"
    """The minimap alone: to its canvas pixel."""


@dataclass(frozen=True, slots=True)
class VirtualPosition:
    """
    Where our character's feet are, in virtual px.

    :ivar x: The feet's x.
    :ivar y: The feet's y.
    :ivar source: `FUSED` from a character on screen; `COARSE` from the
        minimap alone, the middle of the canvas pixel the feet are in.
    """

    x: float
    y: float
    source: PositionSource


@dataclass(frozen=True, slots=True)
class Fusion:
    """
    One read of the position, and what each read said.

    :ivar position: `READ` or `UNSURE`, with why in its detail.
    :ivar minimap: The minimap's feet position, virtual px, rounded; `None`
        when it wasn't read.
    :ivar camera: The camera; `None` when it wasn't read, or wasn't asked.
    :ivar sightings: The characters found, in virtual px; empty when the
        finder wasn't read or wasn't asked.
    :ivar near: How many of them are within `WINDOW` of the minimap's.
    :ivar by_tag: Whether the finder could tell ours apart, so that only a
        sighting it marks ours could be chosen.
    :ivar own_elsewhere: Whether a character the finder marks ours was found
        outside the window: our tag off our character, or the minimap wrong.
    """

    position: Reading[VirtualPosition]
    minimap: tuple[int, int] | None = None
    camera: Camera | None = None
    sightings: tuple[tuple[float, float], ...] = ()
    near: int = 0
    by_tag: bool = False
    own_elsewhere: bool = False


def feet_of_marker(
    transform: MinimapTransform, marker: tuple[float, float]
) -> tuple[float, float]:
    """
    Where a marker's canvas pixel puts the feet, in virtual px: the middle of
    the canvas pixel `FEET_ROWS` below the marker's, as fusion places the
    minimap's position. Also how a target picked in canvas px becomes a
    virtual one.
    """
    half = transform.scale / 2
    corner = transform.to_virtual((marker[0], marker[1] + FEET_ROWS))
    return corner[0] + half, corner[1] + half


def marker_of_feet(
    transform: MinimapTransform, feet: tuple[float, float]
) -> tuple[int, int]:
    """
    The canvas pixel the marker is drawn at for feet at a virtual position:
    `feet_of_marker`'s inverse, for telemetry's canvas-px fields.
    """
    x, y = transform.to_canvas(feet)
    return math.floor(x), math.floor(y) - FEET_ROWS


class CameraSource(Protocol):
    """The part of `CameraReader` fusion calls."""

    def read(self, frame: Frame, seed: Camera | None = None) -> Reading[Camera]: ...


class PositionFusion:
    """
    One map's position reader. It keeps the last camera, to seed the next
    read, and teaches the finder our character wherever the minimap places
    it (`CharacterFinder.learn_own`).
    """

    def __init__(
        self,
        minimap: MinimapTransform,
        camera: Callable[[], CameraSource],
        finder: CharacterFinder,
        *,
        world_map: WorldMap | None = None,
        front_art: Callable[[], FrontArt] | None = None,
    ) -> None:
        """
        :param minimap: The map's minimap transform.
        :param camera: Makes the camera reader, on the first read: indexing a
            map's static render takes time and memory nothing spends before a
            position is asked for.
        :param finder: Finds the characters on screen.
        :param world_map: The map, for the layer our character is drawn on.
        :param front_art: Makes the map's `FrontArt`, the first time our tag
            isn't found. With `world_map`, our tag is then looked for where
            the art drawn in front of our character doesn't hide it; without
            either, it isn't.
        """
        self._transform = minimap
        self._make_camera = camera
        self._finder = finder
        self._world_map = world_map
        self._make_front_art = front_art
        self._last_camera: Camera | None = None
        self._read_camera: Camera | None = None

    @property
    def camera(self) -> Camera | None:
        """
        The camera the last read matched: what places things found on that
        read's frame, such as mobs (`MobsHittingMixin.mobs_in_virtual_px`).
        `None` before the first read, and when the last read matched none
        (the minimap unread, or the camera `UNSURE`): never an older camera.
        """
        return self._read_camera

    @classmethod
    def for_map(
        cls, world_map: WorldMap, frame_check: FrameCheck | None = None
    ) -> PositionFusion:
        """
        The bot's: the map's `CameraReader`, given the bot's `FrameCheck`, and
        a `NameTagFinder`.

        :raises ValueError: The map has no minimap.
        """
        if world_map.minimap is None:
            raise ValueError(f"map {world_map.id} has no minimap")
        return cls(
            world_map.minimap,
            lambda: CameraReader(world_map, frame_check=frame_check),
            NameTagFinder(),
            world_map=world_map,
            front_art=front_art_of(world_map),
        )

    @cached_property
    def _camera(self) -> CameraSource:
        return self._make_camera()

    @cached_property
    def _front_art(self) -> FrontArt | None:
        return None if self._make_front_art is None else self._make_front_art()

    def _hidden(
        self,
        frame: Frame,
        near: tuple[float, float],
        feet: tuple[float, float],
        cam: Camera,
    ) -> CharacterSighting | None:
        """
        Ours, part of its tag hidden by the map's art drawn in front of it:
        looked for when nothing found ours, with the art of the layers above
        the lowest our character could be drawn on near the minimap's feet
        position (`WorldMap.layer_near`). `None` without a map or its art.

        :param near: The minimap's feet position, in client px.
        :param feet: The same, in virtual px.
        """
        if self._world_map is None or self._make_front_art is None:
            return None
        layer = self._world_map.layer_near(feet, WINDOW)
        art = self._front_art
        if layer is None or art is None:
            return None
        covered = _covered_on_screen(art, layer, cam, frame.client_size)
        return self._finder.find_own_hidden(frame, near, covered)

    def read(self, frame: Frame, minimap: Reading[MinimapView]) -> Fusion:
        """
        The position on `frame`.

        :param minimap: The minimap read on the same frame.
        """
        at = frame.captured_at
        self._read_camera = None
        if minimap.value is None:
            why = f"minimap {minimap.status.value}: {minimap.detail}"
            return Fusion(Reading.unsure(at, why))
        marker = minimap.value.self_position
        if marker.value is None:
            why = f"minimap position {marker.status.value}: {marker.detail}"
            return Fusion(Reading.unsure(at, why))
        cell = (marker.value[0], marker.value[1] + FEET_ROWS)
        mx, my = feet_of_marker(self._transform, marker.value)
        seen = Fusion(Reading.unsure(at), (round(mx), round(my)))

        def coarse(why: str) -> Fusion:
            position = VirtualPosition(mx, my, PositionSource.COARSE)
            return replace(seen, position=Reading.read(position, at, why))

        camera = self._camera.read(frame, self._last_camera)
        if camera.value is None:
            return coarse(f"camera {camera.status.value}: {camera.detail}")
        cam = self._last_camera = self._read_camera = camera.value
        seen = replace(seen, camera=cam)
        width, height = frame.client_size
        sx, sy = width / cam.play_area[0], height / cam.play_area[1]
        near = ((mx - cam.x) * sx, (my - cam.y) * sy)
        knows_ours = self._finder.learn_own(frame, near)
        found = self._finder.find(frame)
        if found.value is None:
            return coarse(f"characters {found.status.value}: {found.detail}")
        placed = [
            (cam.to_virtual(s.feet, frame.client_size), s.own) for s in found.value
        ]
        hidden = None
        if knows_ours and not any(own for _, own in placed):
            hidden = self._hidden(frame, near, (mx, my), cam)
            if hidden is not None:
                placed.append((cam.to_virtual(hidden.feet, frame.client_size), True))
        inside = [
            abs(p[0] - mx) <= WINDOW and abs(p[1] - my) <= WINDOW for p, _ in placed
        ]
        near = [place for place, ok in zip(placed, inside, strict=True) if ok]
        seen = replace(
            seen,
            sightings=tuple(p for p, _ in placed),
            near=len(near),
            own_elsewhere=any(
                own and not ok for (_, own), ok in zip(placed, inside, strict=True)
            ),
            by_tag=knows_ours,
        )
        where = f"within {WINDOW} px of the minimap's, of {len(placed)} found"
        candidates = (
            [p for p, own in near if own] if knows_ours else [p for p, _ in near]
        )
        if not candidates:
            whose = "with our tag " if knows_ours else ""
            return coarse(f"no character {whose}{where}")
        if len(candidates) > 1:
            why = f"{len(candidates)} characters {where}, and no telling which is ours"
            return replace(seen, position=Reading.unsure(at, why))
        chosen = candidates[0]
        canvas = self._transform.to_canvas(chosen)
        off = (math.floor(canvas[0]) - cell[0], math.floor(canvas[1]) - cell[1])
        if max(abs(off[0]), abs(off[1])) > AGREE_CELLS:
            why = (
                f"the reads disagree: ({chosen[0]:.1f}, {chosen[1]:.1f}) puts the "
                f"marker {off} canvas px from where it is read"
            )
            return replace(seen, position=Reading.unsure(at, why))
        position = VirtualPosition(chosen[0], chosen[1], PositionSource.FUSED)
        detail = "ours by its tag" if knows_ours else "the one character there"
        if hidden is not None:
            detail += ", part of it behind the map's art"
        return replace(seen, position=Reading.read(position, at, detail))


def front_art_of(world_map: WorldMap) -> Callable[[], FrontArt] | None:
    """
    Makes a map's `FrontArt`, from the extraction its static render is drawn
    from; `None` for a map not loaded from a store.
    """
    render = world_map.static_render
    if render is None:
        return None
    return lambda: FrontArt.load(render.build, render.map_id, render.root)


def _covered_on_screen(
    art: FrontArt, layer: int, cam: Camera, client_size: tuple[int, int]
) -> Callable[[Box], NDArray[np.bool_]]:
    """
    `art.covered` for a character on `layer`, in client px: each client pixel
    takes the virtual pixel its middle falls in, through `cam`. Above 1:1 the
    client upscales the play area bilinearly, which blends art into the
    client pixels around it: those count as covered too.
    """
    sx = client_size[0] / cam.play_area[0]
    sy = client_size[1] / cam.play_area[1]

    def covered(box: Box) -> NDArray[np.bool_]:
        x0, y0, x1, y1 = box
        vx = np.floor((np.arange(x0, x1) + 0.5) / sx + cam.x).astype(np.int64)
        vy = np.floor((np.arange(y0, y1) + 0.5) / sy + cam.y).astype(np.int64)
        left, top = int(vx[0]), int(vy[0])
        drawn = art.covered(layer, (left, top, int(vx[-1]) + 1, int(vy[-1]) + 1))
        mask = drawn[np.ix_(vy - top, vx - left)]
        if sx == 1 and sy == 1:
            return mask
        grown = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8))
        return np.asarray(grown, np.uint8) > 0

    return covered
