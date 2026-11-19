"""
When `AbilityPointDistributor` opens the AP menu: on a level read higher or
different from the last level read. An unreadable level is not a level-up and
doesn't replace the last level read. Stubbed `status_bar` readings, no client.

While it distributes the points it holds a Pause on `Rotation`, released however
the block ends (#443). The Pause, the Supervisor that holds it and the keys it
reads are the production ones; the menu and the clicks are stubbed.
"""

import asyncio
import logging
from collections.abc import Callable

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core.supervisor import PauseKind, Supervisor, resolve_pauses
from botting.screen import Frame, Reading
from maple.decision_makers import Rotation
from maple.decision_makers import ability_point_distributor as module
from maple.decision_makers.ability_point_distributor import AbilityPointDistributor
from maple.decision_makers.providers import (
    ABILITY_MENU,
    AVAILABLE_AP,
    AbilityMenuProvider,
    StatusBarProvider,
)
from maple.screen.status_bar import StatusBar

from .serving import Proxies, serve

FRAME = Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), 0.0, True, True)


def read(level: int) -> Reading[StatusBar]:
    return Reading.read(StatusBar(level, 1, 1, 1, 1, 1, 0.0), 1.0)


def unsure() -> Reading[StatusBar]:
    return Reading.unsure(1.0, "hp: ''")


class Harness:
    """
    The distributor, built and set up as assembly builds it, on a Bot whose status
    bar shows `readings` in turn, one per decision, the first read being setup's.
    """

    def __init__(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        readings: list[Reading[StatusBar]],
    ) -> None:
        monkeypatch.setattr(
            module.controller, "key_binds", lambda ign: {"Ability Menu": "t"}
        )
        self.emitted: list[str] = []
        mocker.patch(
            "botting.core.decision_maker.emit_event",
            side_effect=lambda _cid, event_type, *args, **kwargs: self.emitted.append(
                event_type
            ),
        )
        # The reading `StatusBarProvider` takes at setup comes first.
        reader = mocker.Mock()
        reader.read.side_effect = iter([unsure(), *readings])
        character = mocker.Mock()
        character.main_stat = "STR"
        served = serve(
            monkeypatch,
            pipe=mocker.Mock(),
            frames=lambda: FRAME,
            character=character,
            status_bar=reader,
        )
        self.data = served.data
        served.providers.build([StatusBarProvider])
        self.data.provide(
            ABILITY_MENU,
            object.__new__(AbilityMenuProvider),
            lambda: mocker.Mock(),
            initial_value=mocker.Mock(),
        )
        self.data.provide(AVAILABLE_AP, object.__new__(AbilityMenuProvider), lambda: 5)
        self.menu_opened = mocker.patch.object(module, "ensure_ability_menu_displayed")
        self.distributed: list[tuple[int, list[PauseKind]]] = []
        self.distributor = AbilityPointDistributor({}, self.data, mocker.Mock())  # pyright: ignore[reportArgumentType] - nothing asks it for a proxy
        self.distributor._proxies = Proxies()  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue] - a stand-in
        self.rotation = object.__new__(Rotation)
        self.supervisor = Supervisor(
            "Bot",
            [self.distributor, self.rotation],
            resolve_pauses([AbilityPointDistributor]),
        )
        self.distributor._distribute_ap = self._distribute  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
        self.distributor.setup()

    def _distribute(self, points: int) -> None:
        self.distributed.append((points, self.paused()))

    def paused(self) -> list[PauseKind]:
        """The Pauses held on `Rotation` now."""
        return [pause.kind for pause in self.supervisor.held(Rotation)]

    def decide(self) -> None:
        asyncio.run(self.distributor._decide())  # pyright: ignore[reportPrivateUsage]

    @property
    def opened(self) -> int:
        # Opening and closing the menu are two calls per level-up.
        return self.menu_opened.call_count


@pytest.fixture
def harness(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> Callable[[list[Reading[StatusBar]]], Harness]:
    return lambda readings: Harness(mocker, monkeypatch, readings)


def test_a_higher_level_opens_the_menu_once(harness) -> None:  # noqa: ANN001
    h = harness([read(10), read(10), read(11), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2
    assert [points for points, _ in h.distributed] == [5]
    h.menu_opened.reset_mock()
    h.decide()
    assert h.opened == 0


def test_an_unreadable_level_is_not_a_level_up(harness) -> None:  # noqa: ANN001
    h = harness([read(10), unsure(), unsure()])
    h.decide()
    h.decide()
    assert h.opened == 0


def test_an_unreadable_level_keeps_the_last_one_read(harness) -> None:  # noqa: ANN001
    h = harness([read(10), unsure(), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2


def test_an_unreadable_level_at_startup_makes_the_first_read_the_baseline(
    harness,  # noqa: ANN001
) -> None:
    h = harness([unsure(), read(10), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2


def test_an_unreadable_level_is_logged_once_per_change(
    harness,  # noqa: ANN001
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness([read(10), unsure(), unsure(), read(10), unsure()])
    with caplog.at_level(logging.WARNING, logger=module.logger.name):
        for _ in range(4):
            h.decide()
    assert len(caplog.records) == 2


def test_it_pauses_rotation_only_while_it_distributes(
    harness,  # noqa: ANN001
) -> None:
    h = harness([read(10), read(11)])  # setup reads 10: the decision sees a level-up
    h.decide()

    assert h.distributed == [(5, [PauseKind.SCOPED])]
    assert h.paused() == []
    assert h.emitted.count("decision.paused") == 1
    assert h.emitted.count("decision.resumed") == 1


def test_a_failed_distribution_leaves_rotation_running(
    harness,  # noqa: ANN001
) -> None:
    h = harness([read(10), read(11)])

    def fail(points: int) -> None:
        raise TimeoutError("the menu never showed the points spent")

    h.distributor._distribute_ap = fail  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(TimeoutError):
        h.decide()

    assert h.paused() == []


def test_no_ap_to_distribute_pauses_nothing(
    harness,  # noqa: ANN001
) -> None:
    h = harness([read(10), read(11)])
    h.data._managed[AVAILABLE_AP.name].update_function = lambda: 0  # pyright: ignore[reportPrivateUsage]
    h.decide()

    assert h.distributed == []
    assert h.opened == 2
    assert "decision.paused" not in h.emitted
