"""
The menus Providers (#443): the ability menu's setup, the keys it serves, and
which speed and jump the rotation's physics follow: the menu's when the Bot read
them, the profile's when it did not. No game client: the menu is a stand-in.
"""

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core import BotData
from botting.core.data_keys import resolve_providers
from botting.screen import Frame, Reading
from maple.decision_makers import AbilityPointDistributor, StateSnapshot, mixins
from maple.decision_makers.providers import (
    ABILITY_MENU,
    AVAILABLE_AP,
    INVENTORY_SPACE_LEFT,
    JUMP_MULTIPLIER,
    SPEED_MULTIPLIER,
    AbilityMenuProvider,
    InventoryMenuProvider,
    PathingProvider,
)
from maple.decision_makers.providers import menus as module
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab import corpus
from tests.test_maple.serving import pathing, serve

FRAME = Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), 0.0, True, True)


class _Menu:
    """An ability menu that shows its numbers only while it is open."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.open = False

    def _shown(self, what: str, value: float) -> float:
        assert self.open, f"{what} read with the menu closed"
        self.events.append(what)
        return value

    def is_displayed(self, handle: int, image: object = None) -> bool:
        return self.open

    def get_available_ap(self, handle: int, image: object = None) -> int:
        return int(self._shown("ap", 5))

    def get_speed(self, handle: int, image: object = None) -> float:
        return self._shown("speed", 1.4)

    def get_jump(self, handle: int, image: object = None) -> float:
        return self._shown("jump", 1.1)


@pytest.fixture
def served(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    events: list[str] = []
    menu = _Menu(events)

    def ensure(*, menu: _Menu, ensure_displayed: bool, **kwargs: object) -> None:
        events.append("open" if ensure_displayed else "close")
        menu.open = ensure_displayed

    mocker.patch.object(module, "AbilityMenu", return_value=menu)
    mocker.patch.object(module, "ensure_ability_menu_displayed", side_effect=ensure)
    result = serve(monkeypatch, pipe=mocker.Mock(), frames=lambda: FRAME)
    result.providers.build([AbilityMenuProvider])
    return result, events


def test_the_ability_menu_is_read_while_it_is_open_and_closed_after(served) -> None:  # noqa: ANN001
    result, events = served

    assert events == ["open", "ap", "speed", "jump", "close"]
    data = result.data
    assert data.read(SPEED_MULTIPLIER) == 1.4
    assert data.read(JUMP_MULTIPLIER) == 1.1
    assert data.read(AVAILABLE_AP) == 5
    assert data.read(ABILITY_MENU) is not None


def test_the_multipliers_are_not_refreshed_on_their_own(served) -> None:  # noqa: ANN001
    result, events = served
    events.clear()

    result.data.read(SPEED_MULTIPLIER)
    result.data.read(JUMP_MULTIPLIER)

    assert events == []


def test_the_distributor_builds_the_ability_menu_and_the_snapshot_builds_nothing() -> (
    None
):
    assert AbilityMenuProvider in resolve_providers([AbilityPointDistributor])
    assert resolve_providers([StateSnapshot]) == []


def test_the_inventory_mixin_asks_for_its_provider(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    menu = mocker.Mock(total_slots=24)
    mocker.patch.object(module, "InventoryMenu", return_value=menu)
    menu.get_current_mesos.return_value = 7
    menu.get_active_tab.return_value = "Equip"
    result = serve(monkeypatch, frames=lambda: FRAME)

    class Holder(mixins.MenusMixin):
        data = result.data

    Holder()._create_inventory_menu_attributes()  # pyright: ignore[reportPrivateUsage]
    Holder()._create_inventory_menu_attributes()  # pyright: ignore[reportPrivateUsage]

    assert result.data.is_provided(INVENTORY_SPACE_LEFT)
    assert result.data.inventory_space_left == 24
    assert result.data.current_mesos == 7
    assert [type(p) for p in result.providers].count(InventoryMenuProvider) == 1


# --- the rotation's physics ---------------------------------------------------------


class _Character:
    skills: dict[str, object] = {}  # noqa: RUF012


def _planner(data: BotData | None = None) -> PathingProvider:
    entry = next(e for e in corpus.FIXTURE_MAPS if e.name == "jump_gap")
    reading = Reading.read(VirtualPosition(100.0, 0.0, PositionSource.FUSED), 0.0)
    return pathing(
        corpus.world_map(entry),
        lambda: reading,
        lambda: (300.0, 0.0),
        data=data,
        character=_Character(),
        game_physics=corpus.LAB_PHYSICS_VALUES,
    )


def test_the_physics_follow_the_profile_when_the_menu_was_not_read() -> None:
    planner = _planner()
    planner.data.set_static("speed_multiplier", 1.2)
    planner.data.set_static("jump_multiplier", 1.3)

    base = corpus.LAB_PHYSICS_VALUES
    physics = planner.physics()

    assert physics.walk_speed == pytest.approx(base["walkSpeed"] * 1.2)
    assert physics.jump_speed == pytest.approx(base["jumpSpeed"] * 1.3)


def test_the_physics_follow_the_ability_menu_when_the_bot_read_it() -> None:
    data = BotData("T")
    owner = object.__new__(AbilityMenuProvider)
    data.provide(SPEED_MULTIPLIER, owner, lambda: 1.4)
    data.provide(JUMP_MULTIPLIER, owner, lambda: 1.1)
    planner = _planner(data)

    base = corpus.LAB_PHYSICS_VALUES
    physics = planner.physics()

    assert physics.walk_speed == pytest.approx(base["walkSpeed"] * 1.4)
    assert physics.jump_speed == pytest.approx(base["jumpSpeed"] * 1.1)
