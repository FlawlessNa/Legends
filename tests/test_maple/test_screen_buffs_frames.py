"""
The buffs reader on the real MSCW frame set: every expected `buffs` reading.
The frames' character keeps up Recovery (1001) and Nimble Feet (1002), the
beginner's skills, so the profile's job is any first job. Run with
`pytest -m frames`.
"""

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.buffs import BUFFS, BuffsReader
from maple.screen.locator import FrameCheck
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

NAMES = ("Recovery", "Nimble Feet")


@pytest.fixture(scope="module")
def reader() -> BuffsReader:
    sprites = load_reader_sprites(
        [FRAME_CHECK, BUFFS],
        Profile(job="Swordsman", game_map="x", buffs=NAMES),
        STORE,
        config=CONFIG,
    )
    return BuffsReader(sprites, FrameCheck(sprites))


def test_every_expected_buffs_reading(frames: FrameSet, reader: BuffsReader) -> None:
    """One reader reads the whole set in order, across every client resize."""
    wrong: list[str] = []
    checked = shown = 0
    for entry in frames.entries:
        expected = entry.expect.get("buffs")
        if expected is None:
            continue
        checked += 1
        reading = reader.read(
            Frame(frames.pixels(entry), entry.client_size, 0.0, True, True), NAMES
        )
        value = (
            {name: {"shown": state.shown} for name, state in reading.value.items()}
            if reading.value is not None
            else None
        )
        if reading.value is not None:
            assert all(state.elapsed is None for state in reading.value.values())
            shown += any(state.shown for state in reading.value.values())
        if (reading.status, value) != (expected.status, expected.value):
            wrong.append(
                f"{entry.file}: expected {expected.status.name} {expected.value}, "
                f"got {reading.status.name} {value} {reading.detail}"
            )
    assert checked
    assert shown
    assert not wrong, "\n".join(wrong)


def test_a_block_over_a_slot_never_gives_a_wrong_reading(
    frames: FrameSet, reader: BuffsReader
) -> None:
    """A block, the size of a cursor, painted anywhere over either slot of a
    frame showing both buffs reads them both, or isn't `READ`, once the reader
    has seen the row. Before it has, a block over the edge two slots share
    hides both, and reads as no buff: nothing tells it from no buff at all."""
    entry = next(
        e
        for e in frames.entries
        if e.expect.get("buffs")
        and e.expect["buffs"].status is Status.READ
        and all(v["shown"] for v in e.expect["buffs"].value.values())
    )
    clean = frames.pixels(entry)
    slots = reader.slots(clean)
    assert len(slots) == 2
    assert reader.read(Frame(clean, entry.client_size, 0.0, True, True), NAMES).value
    wrong: list[str] = []
    covered = 0
    for x, y in slots:
        for dx in range(-8, 32, 4):
            for dy in range(-8, 32, 6):
                pixels = clean.copy()
                pixels[max(y + dy, 0) : y + dy + 12, x + dx : x + dx + 12] = (
                    200,
                    100,
                    50,
                )
                reading = reader.read(
                    Frame(pixels, entry.client_size, 0.0, True, True), NAMES
                )
                if reading.status is Status.COVERED:
                    covered += 1
                elif reading.value is None or not all(
                    state.shown for state in reading.value.values()
                ):
                    wrong.append(
                        f"block at {x + dx},{y + dy}: {reading.status.name} "
                        f"{reading.value}"
                    )
    assert covered
    assert not wrong, "\n".join(wrong[:10])
