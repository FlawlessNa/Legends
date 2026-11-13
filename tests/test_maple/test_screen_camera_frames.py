"""
`CameraReader` on the real MSCW frame set, against its `camera` and `map_id`
labels (`tests/frames/README.md`): each map's reader reads its own frames'
cameras, to the pixel at 1:1 and within `SCALED_TOLERANCE` above it, and
every other map's frames as `UNSURE`. Run with `pytest -m frames`; it needs
the game data store, which draws the static renders.
"""

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.model.world import WorldMap
from maple.screen.locator import FrameCheck
from maple.screen.position import Camera, CameraReader, play_area_size
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

DAMP_FOREST = 10005031
MAPS = (DAMP_FOREST, 10002000, 10001000, 10001040)
"""Damp Forest, Ellinia, Henesys, Henesys Market: every map the set shows."""

SCALED_TOLERANCE = 2
"""Virtual px the camera may be off on a client that upscales its play area."""

NEEDS_THE_SEED = {"f063_1920x1080.png", "f064_1920x1080.png"}
"""The Options dialog covers most of the play area: the correlation over the
whole map doesn't propose the camera, the last frame's seeds it."""

MID_RESIZE = {"f043_800x600.png", "f059_1920x1080.png"}
"""The client's picture at the last size, not yet redrawn at the new one."""

DESKTOP = "f002_1366x768.png"
"""The desktop drawn over the client: Damp Forest's art is in the picture,
but it isn't the client's."""


@pytest.fixture(scope="module", params=MAPS)
def reader(request: pytest.FixtureRequest) -> CameraReader:
    """One map's reader at a time, as pytest orders module-scoped params."""
    return CameraReader(WorldMap.load(request.param, root=STORE))


def _frame(frames: FrameSet, entry: FrameEntry) -> Frame:
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def _map_id(entry: FrameEntry) -> int | None:
    expected = entry.expect["map_id"]
    return expected.value if expected.status is Status.READ else None


def _labelled(entry: FrameEntry) -> tuple[int, int] | None:
    expected = entry.expect["camera"]
    if expected.status is not Status.READ:
        return None
    return expected.value["x"], expected.value["y"]


def _own(frames: FrameSet, reader: CameraReader) -> list[FrameEntry]:
    own = [
        e
        for e in sorted(frames.entries, key=lambda e: e.file)
        if _map_id(e) == reader.world_map.id and _labelled(e) is not None
    ]
    assert own
    return own


def _wrong(entry: FrameEntry, camera: Camera | None) -> str | None:
    """Why `camera` isn't the frame's labelled one, or `None` when it is."""
    label = _labelled(entry)
    assert label is not None
    if camera is None:
        return "no camera"
    w, h = entry.client_size
    scaled = w > 1366 or h > 768
    tolerance = SCALED_TOLERANCE if scaled else 0
    off = (camera.x - label[0], camera.y - label[1])
    if max(abs(off[0]), abs(off[1])) > tolerance:
        return f"off by {off}"
    play_area = play_area_size((w, h))
    if camera.play_area != play_area:
        return f"play area {camera.play_area}, expected {play_area}"
    return None


def test_every_frame_of_the_map_reads_its_labelled_camera(
    frames: FrameSet, reader: CameraReader
) -> None:
    """Unseeded: the search over the whole map."""
    wrong: list[str] = []
    for entry in _own(frames, reader):
        reading = reader.read(_frame(frames, entry))
        if entry.file in NEEDS_THE_SEED and reading.status is Status.UNSURE:
            continue
        why = _wrong(entry, reading.value)
        if why:
            wrong.append(
                f"{entry.file}: {why} ({reading.status.name} {reading.detail})"
            )
    assert not wrong, "\n".join(wrong)


def test_a_tracking_run_reads_every_frame_of_the_map(
    frames: FrameSet, reader: CameraReader
) -> None:
    """In name order, each frame seeded by the last camera read, as the
    labels were made. v3's sequences are a frame a second at most, so most
    seeds above 1:1 are too far and fall back to the whole map."""
    wrong: list[str] = []
    seed: Camera | None = None
    for entry in _own(frames, reader):
        reading = reader.read(_frame(frames, entry), seed)
        why = _wrong(entry, reading.value)
        if why:
            wrong.append(
                f"{entry.file}: {why} ({reading.status.name} {reading.detail})"
            )
        seed = reading.value or seed
    assert not wrong, "\n".join(wrong)


def test_every_other_maps_frame_is_unsure(
    frames: FrameSet, reader: CameraReader
) -> None:
    others = [
        e for e in frames.entries if _map_id(e) not in (None, reader.world_map.id)
    ]
    assert others
    read = [
        f"{e.file}: {reading.value}"
        for e in others
        if (reading := reader.read(_frame(frames, e))).status is not Status.UNSURE
    ]
    assert not read, "\n".join(read)


def test_a_frame_caught_mid_resize_is_unsure(
    frames: FrameSet, reader: CameraReader
) -> None:
    """By the match alone: no camera passes the gates."""
    entries = [e for e in frames.entries if e.file in MID_RESIZE]
    assert len(entries) == len(MID_RESIZE)
    for entry in entries:
        assert entry.expect["camera"].status is Status.UNSURE
        reading = reader.read(_frame(frames, entry))
        assert reading.status is Status.UNSURE, f"{entry.file}: {reading}"


def test_the_frame_check_makes_the_untrusted_frames_unsure(frames: FrameSet) -> None:
    """Every frame whose camera is labelled `unsure`, with the bot's frame
    check given. The desktop frame shows Damp Forest's art at a camera the
    match finds, so without the check it reads: the check is what refuses it."""
    sprites = load_reader_sprites(
        [FRAME_CHECK], Profile(job="Swordsman"), STORE, config=CONFIG
    )
    world_map = WorldMap.load(DAMP_FOREST, root=STORE)
    checked = CameraReader(world_map, frame_check=FrameCheck(sprites))
    unchecked = CameraReader(world_map)
    untrusted = [
        e for e in frames.entries if e.expect["camera"].status is Status.UNSURE
    ]
    assert {e.file for e in untrusted} == MID_RESIZE | {DESKTOP}
    for entry in untrusted:
        reading = checked.read(_frame(frames, entry))
        assert reading.status is Status.UNSURE, f"{entry.file}: {reading}"
    (desktop,) = (e for e in untrusted if e.file == DESKTOP)
    assert unchecked.read(_frame(frames, desktop)).status is Status.READ
