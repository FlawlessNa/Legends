"""
`CameraReader` on a synthetic map: a render of smooth colour with fine noise,
so that its colours are rare and its coarse shape is distinct, as a map's art
is. A 1:1 client is a crop of it; a client above 1:1 is a crop upscaled
bilinearly, as the client upscales its play area.
"""

from functools import cache

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from botting.screen import Frame, Status
from game_data.catalogue import Bounds
from maple.model.world import WorldMap
from maple.screen.position import Camera, CameraReader
from maple.screen.position.camera import MIN_SHARE, MIN_SHARPNESS, play_area_widths

RENDER_SIZE = (2400, 1400)
BOUNDS = Bounds(left=-1000, top=-600, right=1400, bottom=800)


@cache
def synthetic_render(width: int, height: int, seed: int) -> NDArray[np.uint8]:
    """RGBA, opaque: smooth colour (0 to 200) plus noise (0 to 55)."""
    rng = np.random.default_rng(seed)
    coarse = rng.integers(0, 200, (height // 80 + 2, width // 80 + 2, 3))
    smooth = cv2.resize(
        coarse.astype(np.float32), (width, height), interpolation=cv2.INTER_CUBIC
    )
    noise = rng.integers(0, 56, (height, width, 3))
    rgb = np.clip(smooth, 0, 200).astype(np.int32) + noise
    alpha = np.full((height, width, 1), 255)
    return np.concatenate([rgb, alpha], axis=2).astype(np.uint8)


def world_map(bounds: Bounds = BOUNDS) -> WorldMap:
    return WorldMap(
        id=1,
        name=None,
        street=None,
        bounds=bounds,
        minimap=None,
        platforms=(),
        walls=(),
        ropes=(),
        portals=(),
    )


@cache
def reader() -> CameraReader:
    return CameraReader(world_map(), render=synthetic_render(*RENDER_SIZE, 1))


def crop(
    cam: tuple[int, int], size: tuple[int, int], seed: int = 1
) -> NDArray[np.uint8]:
    """The play area, BGR, with the camera at `cam` in render px."""
    rgba = synthetic_render(*RENDER_SIZE, seed)
    x, y = cam
    return np.ascontiguousarray(rgba[y : y + size[1], x : x + size[0], 2::-1])


def frame(pixels: NDArray[np.uint8], ok: bool = True) -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 3.0, True, ok, "" if ok else "moved")


def resized(pixels: NDArray[np.uint8], size: tuple[int, int]) -> NDArray[np.uint8]:
    """Bilinearly, as the client upscales its play area."""
    out = cv2.resize(pixels, size, interpolation=cv2.INTER_LINEAR)
    return np.asarray(out, dtype=np.uint8)


def upscaled(
    cam: tuple[int, int], view: tuple[int, int], client: tuple[int, int]
) -> Frame:
    return frame(resized(crop(cam, view), client))


def virtual(cam: tuple[int, int]) -> tuple[int, int]:
    return cam[0] + BOUNDS.left, cam[1] + BOUNDS.top


def placed(camera: Camera | None) -> tuple[int, int] | None:
    return None if camera is None else (camera.x, camera.y)


@pytest.mark.parametrize(
    ("cam", "size"),
    [
        ((0, 0), (800, 600)),
        ((1234, 567), (1024, 768)),
        ((1034, 632), (1366, 768)),
        ((1600, 800), (800, 600)),
    ],
)
def test_a_1_to_1_frame_reads_its_camera_to_the_pixel(
    cam: tuple[int, int], size: tuple[int, int]
) -> None:
    reading = reader().read(frame(crop(cam, size)))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert placed(reading.value) == virtual(cam)
    assert reading.value.play_area == size
    assert reading.value.share >= MIN_SHARE
    assert reading.value.sharpness >= MIN_SHARPNESS


@pytest.mark.parametrize("seed_offset", [(40, -25), (900, 500)])
def test_a_seed_near_or_far_gives_the_same_camera(
    seed_offset: tuple[int, int],
) -> None:
    """A seed is searched around first; one that isn't confirmed there falls
    back to the whole map, never to the seed's neighbourhood's best."""
    cam = (700, 400)
    x, y = virtual((cam[0] + seed_offset[0], cam[1] + seed_offset[1]))
    seed = Camera(x, y, 0.9, 3.0, (1024, 768))

    reading = reader().read(frame(crop(cam, (1024, 768))), seed)

    assert placed(reading.value) == virtual(cam), reading.detail


def test_another_maps_frame_is_unsure() -> None:
    reading = reader().read(frame(crop((500, 300), (1024, 768), seed=2)))

    assert reading.status is Status.UNSURE
    assert reading.value is None


def test_a_frame_mostly_under_a_window_is_unsure() -> None:
    """Too little of the art is drawn for the share to pass: never the camera
    the few visible pixels suggest."""
    pixels = crop((500, 300), (1024, 768))
    pixels[:, 60:] = (230, 220, 210)

    assert reader().read(frame(pixels)).status is Status.UNSURE


def test_a_frame_caught_mid_resize_is_unsure() -> None:
    """The client's picture still at the last size, squeezed into the new one."""
    squeezed = resized(crop((500, 300), (1366, 768)), (800, 600))

    assert reader().read(frame(squeezed)).status is Status.UNSURE


def test_a_frame_that_is_not_ok_is_unsure() -> None:
    reading = reader().read(frame(crop((500, 300), (800, 600)), ok=False))

    assert reading.status is Status.UNSURE
    assert "moved" in reading.detail


@pytest.mark.parametrize(
    ("view", "client"),
    [
        ((1366, 768), (1920, 1080)),
        ((1228, 768), (1920, 1200)),
        ((1366, 768), (2560, 1440)),
    ],
)
def test_an_upscaled_frame_reads_its_camera_and_play_area(
    view: tuple[int, int], client: tuple[int, int]
) -> None:
    cam = (612, 345)

    reading = reader().read(upscaled(cam, view, client))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert placed(reading.value) == virtual(cam)
    assert reading.value.play_area == view


def test_an_upscaled_frame_reads_the_same_seeded() -> None:
    cam = (612, 345)
    x, y = virtual((cam[0] + 7, cam[1] - 5))
    seed = Camera(x, y, 0.9, 3.0, (1366, 768))

    reading = reader().read(upscaled(cam, (1366, 768), (1920, 1080)), seed)

    assert placed(reading.value) == virtual(cam), reading.detail
    assert reading.detail.startswith("scaled seeded")


def test_an_upscaled_frame_of_another_map_is_unsure() -> None:
    pixels = crop((612, 345), (1366, 768), seed=2)
    other = frame(resized(pixels, (1920, 1080)))

    assert reader().read(other).status is Status.UNSURE


@pytest.mark.parametrize(
    ("client", "widths"),
    [
        ((1920, 1080), (1365, 1366)),
        ((1920, 1200), (1228, 1229)),
        ((2048, 768), (2048,)),
    ],
)
def test_the_play_area_widths_tried(
    client: tuple[int, int], widths: tuple[int, ...]
) -> None:
    assert play_area_widths(*client) == widths


def test_a_map_without_a_static_render_is_refused() -> None:
    with pytest.raises(ValueError, match="no static render"):
        CameraReader(world_map())
