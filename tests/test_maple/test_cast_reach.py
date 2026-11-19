"""
`CAST_REACH` (#578): how far the training skill reaches, in client px, and how
many mobs make a cast worth it, from the profile and the character's skills.

No game client: the character is a stand-in with real `MapleSkill`s, served by
its Bot-level Provider (`serving.serve`).
"""

from dataclasses import dataclass, field

import pytest

from maple.decision_makers.providers import CAST_REACH, CastReach, CastReachProvider
from maple.model.characters.maple_skills import MapleSkill
from maple.screen.position.camera import Camera
from tests.test_maple.serving import serve

#: Declares the up and the down ranges beside the vertical one.
SPLIT = MapleSkill(
    "Split",
    "Attack",
    horizontal_screen_range=400,
    vertical_screen_range=300,
    vertical_up_screen_range=500,
    vertical_down_screen_range=100,
)
#: Declares the vertical range alone.
PLAIN = MapleSkill(
    "Plain", "Attack", horizontal_screen_range=300, vertical_screen_range=200
)
#: Declares no range at all.
BLIND = MapleSkill("Blind", "Attack")


@dataclass
class Character:
    main_skill: str = "Plain"
    skills: dict[str, MapleSkill] = field(
        default_factory=lambda: {s.name: s for s in (SPLIT, PLAIN, BLIND)}
    )


def reach(monkeypatch: pytest.MonkeyPatch, **settings: object) -> CastReach | None:
    served = serve(monkeypatch, character=Character())
    served.providers.settings.update(settings)
    served.providers.build([CastReachProvider])
    return served.data.read(CAST_REACH)


def test_left_and_right_are_half_the_horizontal_range_up_and_down_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = reach(monkeypatch, mob_count_threshold=3, training_skill="Split")

    assert found == CastReach(left=200, right=200, up=250, down=50, min_mobs=3)


def test_up_and_down_are_half_the_vertical_range_when_theirs_are_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = reach(monkeypatch, mob_count_threshold=2, training_skill="Plain")

    assert found == CastReach(left=150, right=150, up=100, down=100, min_mobs=2)


def test_the_main_skill_is_taken_with_no_training_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = reach(monkeypatch, mob_count_threshold=4)

    assert found is not None
    assert (found.left, found.up, found.min_mobs) == (150, 100, 4)


def test_it_is_none_with_no_mob_count_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert reach(monkeypatch, training_skill="Split") is None


def test_it_is_none_for_a_skill_with_no_range(monkeypatch: pytest.MonkeyPatch) -> None:
    assert reach(monkeypatch, mob_count_threshold=3, training_skill="Blind") is None


def test_in_virtual_scales_as_the_camera_scales_a_point() -> None:
    """A client of 1600 by 900 showing a play area of 1280 by 720: a client px
    is 0.8 virtual px each way."""
    found = CastReach(left=200, right=100, up=250, down=50, min_mobs=3)
    camera = Camera(x=0, y=0, share=1.0, sharpness=1.0, play_area=(1280, 720))
    client = (1600, 900)

    left, right, up, down = found.in_virtual(client, camera.play_area)

    assert (left, right, up, down) == (160, 80, 200, 40)
    # The same scale as a point's distance from the camera's corner.
    assert camera.to_virtual((found.left, found.up), client) == (left, up)
