import pytest
from pytest_mock import MockerFixture, MockType

from botting.core.bot_data import BotData


@pytest.fixture
def bot_data() -> BotData:
    return BotData("TestBot")


@pytest.fixture
def mock_fn(mocker: MockerFixture) -> MockType:
    return mocker.Mock(return_value="new_value")


# --- create_attribute ---------------------------------------------------------


def test_initializes_metadata(bot_data: BotData, mock_fn: MockType) -> None:
    bot_data.create_attribute("test_attr", mock_fn)
    assert "test_attr" in bot_data._managed
    assert bot_data._managed["test_attr"].metadata.update_count == 1


def test_sets_initial_value_via_update(bot_data: BotData, mock_fn: MockType) -> None:
    bot_data.create_attribute("test_attr", mock_fn)
    assert bot_data.test_attr == "new_value"


def test_with_explicit_initial_value(bot_data: BotData, mocker: MockerFixture) -> None:
    fn = mocker.Mock(return_value="should_not_be_used")
    bot_data.create_attribute("x", fn, initial_value="preset")
    assert bot_data._managed["x"].value == "preset"
    fn.assert_not_called()


def test_falsy_initial_value_bypasses_update(
    bot_data: BotData, mocker: MockerFixture
) -> None:
    fn = mocker.Mock(return_value="should_not_be_used")
    bot_data.create_attribute("x", fn, initial_value=False)
    assert bot_data._managed["x"].value is False
    fn.assert_not_called()


def test_raises_if_already_exists(bot_data: BotData, mock_fn: MockType) -> None:
    bot_data.create_attribute("x", mock_fn)
    with pytest.raises(AttributeError):
        bot_data.create_attribute("x", mock_fn)


def test_with_threshold(bot_data: BotData, mock_fn: MockType) -> None:
    bot_data.create_attribute("x", mock_fn, threshold=1.0)
    assert bot_data._managed["x"].threshold == 1.0


def test_create_attribute_promotes_static(bot_data: BotData, mock_fn: MockType) -> None:
    bot_data.set_static("x", "static_val")
    bot_data.create_attribute("x", mock_fn)
    assert "x" not in bot_data._static
    assert "x" in bot_data._managed
    assert bot_data.x == "new_value"


# --- static attributes --------------------------------------------------------


def test_set_and_get_static(bot_data: BotData) -> None:
    bot_data.set_static("handle", 12345)
    assert bot_data.handle == 12345


def test_overwrite_static(bot_data: BotData) -> None:
    bot_data.set_static("x", 1)
    bot_data.set_static("x", 2)
    assert bot_data.x == 2


def test_setattr_on_static(bot_data: BotData) -> None:
    bot_data.set_static("x", 1)
    bot_data.x = 42
    assert bot_data.x == 42


def test_managed_takes_priority_over_static(
    bot_data: BotData, mocker: MockerFixture
) -> None:
    mock_fn = mocker.Mock(return_value="managed_val")
    bot_data.create_attribute("x", mock_fn)
    bot_data._static["x"] = "static_val"
    assert bot_data.x == "managed_val"


# --- error handling -----------------------------------------------------------


def test_error_handler_called_on_failure(
    bot_data: BotData, mocker: MockerFixture
) -> None:
    calls = []

    def failing_then_ok() -> str:
        calls.append(1)
        if len(calls) <= 1:
            raise ValueError("fail")
        return "ok"

    handler = mocker.Mock()
    bot_data.create_attribute("x", failing_then_ok, error_handler=handler)
    assert bot_data.x == "ok"
    handler.assert_called_once()


def test_error_raised_without_handler(bot_data: BotData, mocker: MockerFixture) -> None:
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = mocker.Mock(side_effect=ValueError("fail"))
    with pytest.raises(ValueError, match="fail"):
        bot_data.update_attribute("x")


def test_max_retries_caps_recursion(bot_data: BotData, mocker: MockerFixture) -> None:
    """Error handler that never fixes the problem stops after max_retries."""
    fn = mocker.Mock(side_effect=ValueError("always fails"))
    handler = mocker.Mock()
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = fn
    bot_data._managed["x"].error_handler = handler
    bot_data._managed["x"].max_retries = 2
    with pytest.raises(ValueError, match="always fails"):
        bot_data.update_attribute("x")
    assert handler.call_count == 2


def test_max_retries_default_is_one(bot_data: BotData, mocker: MockerFixture) -> None:
    fn = mocker.Mock(side_effect=ValueError("always fails"))
    handler = mocker.Mock()
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = fn
    bot_data._managed["x"].error_handler = handler
    with pytest.raises(ValueError, match="always fails"):
        bot_data.update_attribute("x")
    assert handler.call_count == 1


# --- attribute access ---------------------------------------------------------


class FakeClock:
    """A monotonic clock that moves only when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_getattr_auto_refreshes_once_the_threshold_has_passed(
    mocker: MockerFixture,
) -> None:
    clock = FakeClock()
    bot_data = BotData("TestBot", clock=clock)
    mock_fn = mocker.Mock(return_value="initial")
    bot_data.create_attribute("x", mock_fn, threshold=0.5)
    mock_fn.return_value = "refreshed"

    clock.advance(0.5)
    assert bot_data.x == "initial"
    clock.advance(0.25)
    assert bot_data.x == "refreshed"
    assert mock_fn.call_count == 2


def test_an_attribute_with_no_threshold_never_refreshes_on_read(
    mocker: MockerFixture,
) -> None:
    clock = FakeClock()
    bot_data = BotData("TestBot", clock=clock)
    mock_fn = mocker.Mock(return_value="initial")
    bot_data.create_attribute("x", mock_fn)
    clock.advance(1e9)
    _ = bot_data.x
    assert mock_fn.call_count == 1


def test_an_attribute_given_an_initial_value_refreshes_on_its_first_read(
    mocker: MockerFixture,
) -> None:
    bot_data = BotData("TestBot", clock=FakeClock())
    mock_fn = mocker.Mock(return_value="fresh")
    bot_data.create_attribute("x", mock_fn, threshold=60.0, initial_value="preset")
    assert bot_data.x == "fresh"


def test_time_queries_read_the_injected_clock(mocker: MockerFixture) -> None:
    clock = FakeClock()
    bot_data = BotData("TestBot", clock=clock)
    values = iter(["a", "a", None])
    bot_data.create_attribute("x", mocker.Mock(side_effect=lambda: next(values)))
    clock.advance(3)
    bot_data.update_attribute("x")  # same value, still valid
    assert bot_data.get_time_since_last_valid_update("x") == 0
    assert bot_data.get_time_since_last_value_change("x") == 3
    clock.advance(2)
    bot_data.update_attribute("x")  # None: a change, but not valid
    clock.advance(1)
    assert bot_data.get_time_since_last_valid_update("x") == 3
    assert bot_data.get_time_since_last_value_change("x") == 1


def test_an_attribute_never_validly_updated_is_infinitely_stale(
    mocker: MockerFixture,
) -> None:
    bot_data = BotData("TestBot", clock=FakeClock())
    bot_data.create_attribute("x", mocker.Mock(return_value=None))
    assert bot_data.get_time_since_last_valid_update("x") == float("inf")


def test_getattr_increments_access_count(
    bot_data: BotData, mocker: MockerFixture
) -> None:
    mock_fn = mocker.Mock(return_value="val")
    bot_data.create_attribute("x", mock_fn)
    _ = bot_data.x
    assert bot_data._managed["x"].metadata.access_count == 1


def test_setattr_on_managed(bot_data: BotData, mocker: MockerFixture) -> None:
    mock_fn = mocker.Mock(return_value="val")
    bot_data.create_attribute("x", mock_fn)
    bot_data.x = "manual"
    assert bot_data.x == "manual"
    assert "manual" in bot_data._managed["x"].metadata.prev_values


def test_setattr_on_unknown_raises(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        bot_data.unknown = "value"


def test_an_unregistered_has_name_raises_like_any_other(bot_data: BotData) -> None:
    """No feature flags: a `has_*` name nothing registered is not False."""
    with pytest.raises(AttributeError, match="has_minimap_attributes"):
        _ = bot_data.has_minimap_attributes


def test_getattr_on_unknown_raises(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        _ = bot_data.unknown


def test_ign_is_normal_attribute(bot_data: BotData) -> None:
    assert bot_data.ign == "TestBot"
    bot_data.ign = "NewBot"
    assert bot_data.ign == "NewBot"


def test_update_attribute_updates_value(
    bot_data: BotData, mocker: MockerFixture
) -> None:
    mock_fn = mocker.Mock(return_value="initial")
    bot_data.create_attribute("x", mock_fn)
    mock_fn.return_value = "updated"
    bot_data.update_attribute("x")
    assert bot_data.x == "updated"
    assert bot_data._managed["x"].metadata.update_count == 2


def test_update_attribute_raises_for_unknown(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        bot_data.update_attribute("nonexistent")


# --- query methods ------------------------------------------------------------


def test_get_time_since_last_valid_update(bot_data: BotData) -> None:
    bot_data.create_attribute("x", lambda: "valid")
    elapsed = bot_data.get_time_since_last_valid_update("x")
    assert elapsed >= 0
    assert elapsed < 1


def test_get_time_since_last_valid_update_raises_for_unknown(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        bot_data.get_time_since_last_valid_update("unknown")


def test_get_time_since_last_value_change(bot_data: BotData) -> None:
    bot_data.create_attribute("x", lambda: "val")
    elapsed = bot_data.get_time_since_last_value_change("x")
    assert elapsed >= 0
    assert elapsed < 1


def test_get_time_since_last_value_change_raises_for_unknown(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        bot_data.get_time_since_last_value_change("unknown")


def test_check_if_values_have_changed_false_for_static(bot_data: BotData) -> None:
    bot_data.create_attribute("x", lambda: 42)
    for _ in range(5):
        bot_data.update_attribute("x")
    assert not bot_data.check_if_values_have_changed("x")


def test_check_if_values_have_changed_true_for_changing(bot_data: BotData) -> None:
    counter = [0]
    bot_data.create_attribute(
        "x", lambda: (counter.__setitem__(0, counter[0] + 1), counter[0])[1]
    )
    for _ in range(3):
        bot_data.update_attribute("x")
    assert bot_data.check_if_values_have_changed("x")


def test_check_if_values_have_changed_raises_for_unknown(bot_data: BotData) -> None:
    with pytest.raises(AttributeError):
        bot_data.check_if_values_have_changed("unknown")
