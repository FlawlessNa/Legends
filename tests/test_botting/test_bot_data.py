from datetime import datetime, timedelta

import pytest
from pytest_mock import MockType

from botting.core.bot_data import BotData, ManagedAttribute, _SENTINEL


@pytest.fixture
def bot_data() -> BotData:
    return BotData("TestBot")


@pytest.fixture
def mock_fn(mocker) -> MockType:
    return mocker.Mock(return_value="new_value")


# --- create_attribute ---------------------------------------------------------


def test_initializes_metadata(bot_data, mock_fn):
    bot_data.create_attribute("test_attr", mock_fn)
    assert "test_attr" in bot_data._managed
    assert bot_data._managed["test_attr"].metadata.update_count == 1


def test_sets_initial_value_via_update(bot_data, mock_fn):
    bot_data.create_attribute("test_attr", mock_fn)
    assert bot_data.test_attr == "new_value"


def test_with_explicit_initial_value(bot_data, mocker):
    fn = mocker.Mock(return_value="should_not_be_used")
    bot_data.create_attribute("x", fn, initial_value="preset")
    assert bot_data._managed["x"].value == "preset"
    fn.assert_not_called()


def test_falsy_initial_value_bypasses_update(bot_data, mocker):
    fn = mocker.Mock(return_value="should_not_be_used")
    bot_data.create_attribute("x", fn, initial_value=False)
    assert bot_data._managed["x"].value is False
    fn.assert_not_called()


def test_raises_if_already_exists(bot_data, mock_fn):
    bot_data.create_attribute("x", mock_fn)
    with pytest.raises(AttributeError):
        bot_data.create_attribute("x", mock_fn)


def test_with_threshold(bot_data, mock_fn):
    bot_data.create_attribute("x", mock_fn, threshold=1.0)
    assert bot_data._managed["x"].threshold == 1.0


# --- reconfigure_attribute ----------------------------------------------------


def test_preserves_metadata_history(bot_data, mock_fn, mocker):
    bot_data.create_attribute("x", mock_fn)
    original_metadata = bot_data._managed["x"].metadata
    new_fn = mocker.Mock(return_value="updated")
    bot_data.reconfigure_attribute("x", update_function=new_fn, threshold=1.0)
    assert bot_data._managed["x"].metadata is original_metadata


def test_updates_function_and_threshold(bot_data, mock_fn, mocker):
    bot_data.create_attribute("x", mock_fn, threshold=0.5)
    new_fn = mocker.Mock(return_value="updated")
    bot_data.reconfigure_attribute("x", update_function=new_fn, threshold=2.0)
    assert bot_data._managed["x"].update_function is new_fn
    assert bot_data._managed["x"].threshold == 2.0


def test_can_set_error_handler_to_none(bot_data, mocker):
    handler = mocker.Mock()
    bot_data.create_attribute("x", mocker.Mock(return_value=1), error_handler=handler)
    bot_data.reconfigure_attribute("x", error_handler=None)
    assert bot_data._managed["x"].error_handler is None


def test_leaves_unspecified_fields_unchanged(bot_data, mock_fn):
    bot_data.create_attribute("x", mock_fn, threshold=0.5)
    bot_data.reconfigure_attribute("x", threshold=2.0)
    # update_function should be unchanged
    assert bot_data._managed["x"].update_function is mock_fn
    assert bot_data._managed["x"].threshold == 2.0


def test_raises_for_unknown(bot_data):
    with pytest.raises(AttributeError):
        bot_data.reconfigure_attribute("nonexistent", update_function=lambda: 1)


# --- create_or_reconfigure_attribute ------------------------------------------


def test_creates_when_new(bot_data, mock_fn):
    bot_data.create_or_reconfigure_attribute("x", mock_fn)
    assert "x" in bot_data._managed
    assert bot_data.x == "new_value"


def test_reconfigures_when_existing(bot_data, mock_fn, mocker):
    bot_data.create_attribute("x", mock_fn)
    original_metadata = bot_data._managed["x"].metadata
    new_fn = mocker.Mock(return_value="updated")
    bot_data.create_or_reconfigure_attribute("x", new_fn, threshold=1.0)
    assert bot_data._managed["x"].metadata is original_metadata
    assert bot_data._managed["x"].update_function is new_fn
    assert bot_data._managed["x"].threshold == 1.0


def test_promotes_static_to_managed(bot_data, mock_fn):
    bot_data.set_static("x", "static_val")
    bot_data.create_or_reconfigure_attribute("x", mock_fn)
    assert "x" not in bot_data._static
    assert "x" in bot_data._managed
    assert bot_data.x == "new_value"


def test_create_attribute_promotes_static(bot_data, mock_fn):
    bot_data.set_static("x", "static_val")
    bot_data.create_attribute("x", mock_fn)
    assert "x" not in bot_data._static
    assert "x" in bot_data._managed
    assert bot_data.x == "new_value"


# --- static attributes --------------------------------------------------------


def test_set_and_get_static(bot_data):
    bot_data.set_static("handle", 12345)
    assert bot_data.handle == 12345


def test_overwrite_static(bot_data):
    bot_data.set_static("x", 1)
    bot_data.set_static("x", 2)
    assert bot_data.x == 2


def test_setattr_on_static(bot_data):
    bot_data.set_static("x", 1)
    bot_data.x = 42
    assert bot_data.x == 42


def test_managed_takes_priority_over_static(bot_data, mocker):
    mock_fn = mocker.Mock(return_value="managed_val")
    bot_data.create_attribute("x", mock_fn)
    bot_data._static["x"] = "static_val"
    assert bot_data.x == "managed_val"


# --- feature flags ------------------------------------------------------------


def test_unregistered_has_returns_false(bot_data):
    assert not bot_data.has_minimap_attributes
    assert not bot_data.has_smart_rotation
    assert not bot_data.has_rotation_attributes


def test_set_feature(bot_data):
    bot_data.set_feature("has_minimap_attributes")
    assert bot_data.has_minimap_attributes


def test_remove_feature(bot_data):
    bot_data.set_feature("has_minimap_attributes")
    bot_data.remove_feature("has_minimap_attributes")
    assert not bot_data.has_minimap_attributes


def test_remove_nonexistent_feature_is_safe(bot_data):
    bot_data.remove_feature("has_nonexistent")  # should not raise


# --- error handling -----------------------------------------------------------


def test_error_handler_called_on_failure(bot_data, mocker):
    calls = []

    def failing_then_ok():
        calls.append(1)
        if len(calls) <= 1:
            raise ValueError("fail")
        return "ok"

    handler = mocker.Mock()
    bot_data.create_attribute("x", failing_then_ok, error_handler=handler)
    assert bot_data.x == "ok"
    handler.assert_called_once()


def test_error_raised_without_handler(bot_data, mocker):
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = mocker.Mock(side_effect=ValueError("fail"))
    with pytest.raises(ValueError):
        bot_data.update_attribute("x")


def test_max_retries_caps_recursion(bot_data, mocker):
    """Error handler that never fixes the problem stops after max_retries."""
    fn = mocker.Mock(side_effect=ValueError("always fails"))
    handler = mocker.Mock()
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = fn
    bot_data._managed["x"].error_handler = handler
    bot_data._managed["x"].max_retries = 2
    with pytest.raises(ValueError):
        bot_data.update_attribute("x")
    assert handler.call_count == 2


def test_max_retries_default_is_one(bot_data, mocker):
    fn = mocker.Mock(side_effect=ValueError("always fails"))
    handler = mocker.Mock()
    bot_data.create_attribute("x", lambda: 1)
    bot_data._managed["x"].update_function = fn
    bot_data._managed["x"].error_handler = handler
    with pytest.raises(ValueError):
        bot_data.update_attribute("x")
    assert handler.call_count == 1


# --- attribute access ---------------------------------------------------------


def test_getattr_auto_refreshes_on_threshold(bot_data, mocker):
    mock_fn = mocker.Mock(return_value="initial")
    bot_data.create_attribute("x", mock_fn, threshold=0.1)
    bot_data._managed["x"].metadata.last_update_time = datetime.now() - timedelta(
        seconds=0.2
    )
    mock_fn.return_value = "refreshed"
    assert bot_data.x == "refreshed"


def test_getattr_increments_access_count(bot_data, mocker):
    mock_fn = mocker.Mock(return_value="val")
    bot_data.create_attribute("x", mock_fn)
    _ = bot_data.x
    assert bot_data._managed["x"].metadata.access_count == 1


def test_setattr_on_managed(bot_data, mocker):
    mock_fn = mocker.Mock(return_value="val")
    bot_data.create_attribute("x", mock_fn)
    bot_data.x = "manual"
    assert bot_data.x == "manual"
    assert "manual" in bot_data._managed["x"].metadata.prev_values


def test_setattr_on_unknown_raises(bot_data):
    with pytest.raises(AttributeError):
        bot_data.unknown = "value"


def test_getattr_on_unknown_raises(bot_data):
    with pytest.raises(AttributeError):
        _ = bot_data.unknown


def test_ign_is_normal_attribute(bot_data):
    assert bot_data.ign == "TestBot"
    bot_data.ign = "NewBot"
    assert bot_data.ign == "NewBot"


def test_update_attribute_updates_value(bot_data, mocker):
    mock_fn = mocker.Mock(return_value="initial")
    bot_data.create_attribute("x", mock_fn)
    mock_fn.return_value = "updated"
    bot_data.update_attribute("x")
    assert bot_data.x == "updated"
    assert bot_data._managed["x"].metadata.update_count == 2


def test_update_attribute_raises_for_unknown(bot_data):
    with pytest.raises(AttributeError):
        bot_data.update_attribute("nonexistent")


# --- query methods ------------------------------------------------------------


def test_get_time_since_last_valid_update(bot_data):
    bot_data.create_attribute("x", lambda: "valid")
    elapsed = bot_data.get_time_since_last_valid_update("x")
    assert elapsed >= 0
    assert elapsed < 1


def test_get_time_since_last_valid_update_raises_for_unknown(bot_data):
    with pytest.raises(AttributeError):
        bot_data.get_time_since_last_valid_update("unknown")


def test_get_time_since_last_value_change(bot_data):
    bot_data.create_attribute("x", lambda: "val")
    elapsed = bot_data.get_time_since_last_value_change("x")
    assert elapsed >= 0
    assert elapsed < 1


def test_get_time_since_last_value_change_raises_for_unknown(bot_data):
    with pytest.raises(AttributeError):
        bot_data.get_time_since_last_value_change("unknown")


def test_check_if_values_have_changed_false_for_static(bot_data):
    bot_data.create_attribute("x", lambda: 42)
    for _ in range(5):
        bot_data.update_attribute("x")
    assert not bot_data.check_if_values_have_changed("x")


def test_check_if_values_have_changed_true_for_changing(bot_data):
    counter = [0]
    bot_data.create_attribute(
        "x", lambda: (counter.__setitem__(0, counter[0] + 1), counter[0])[1]
    )
    for _ in range(3):
        bot_data.update_attribute("x")
    assert bot_data.check_if_values_have_changed("x")


def test_check_if_values_have_changed_raises_for_unknown(bot_data):
    with pytest.raises(AttributeError):
        bot_data.check_if_values_have_changed("unknown")


# --- snapshot / restore -------------------------------------------------------
# A DecisionMaker may temporarily hijack an attribute another one owns. Snapshot and
# restore let it hand the exact original configuration back, rather than re-deriving it
# (which rebinds owner methods to the hijacker).


@pytest.fixture
def original(mocker) -> MockType:
    return mocker.Mock(return_value="original")


@pytest.fixture
def snapshot_data(bot_data, original) -> BotData:
    bot_data.create_attribute("x", original, threshold=1.0, initial_value="seed")
    return bot_data


def test_restores_the_exact_update_function(snapshot_data, original):
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute("x", update_function=lambda: "hijacked")
    snapshot_data.update_attribute("x")
    assert snapshot_data.x == "hijacked"

    snapshot_data.restore_attribute("x")
    assert snapshot_data._managed["x"].update_function is original
    snapshot_data.update_attribute("x")
    assert snapshot_data.x == "original"


def test_restores_the_full_configuration(snapshot_data, mocker):
    handler = mocker.Mock()
    snapshot_data.reconfigure_attribute("x", error_handler=handler)
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute(
        "x", update_function=lambda: "hijacked", threshold=99.0, error_handler=None
    )

    snapshot_data.restore_attribute("x")
    managed = snapshot_data._managed["x"]
    assert managed.threshold == 1.0
    assert managed.error_handler is handler


def test_first_snapshot_wins(snapshot_data, original):
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute("x", update_function=lambda: "first")
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute("x", update_function=lambda: "second")

    snapshot_data.restore_attribute("x")
    assert snapshot_data._managed["x"].update_function is original


def test_restore_is_a_noop_without_a_snapshot(snapshot_data, mocker):
    hijack = mocker.Mock(return_value="hijacked")
    snapshot_data.reconfigure_attribute("x", update_function=hijack)
    snapshot_data.restore_attribute("x")
    assert snapshot_data._managed["x"].update_function is hijack


def test_restore_only_once_per_snapshot(snapshot_data, mocker):
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute("x", update_function=lambda: "hijacked")
    snapshot_data.restore_attribute("x")

    later = mocker.Mock(return_value="later")
    snapshot_data.reconfigure_attribute("x", update_function=later)
    snapshot_data.restore_attribute("x")
    assert snapshot_data._managed["x"].update_function is later


def test_restore_preserves_value_and_metadata(snapshot_data):
    snapshot_data.snapshot_attribute("x")
    snapshot_data.reconfigure_attribute("x", update_function=lambda: "hijacked")
    snapshot_data.update_attribute("x")
    update_count = snapshot_data._managed["x"].metadata.update_count

    snapshot_data.restore_attribute("x")
    managed = snapshot_data._managed["x"]
    assert managed.value == "hijacked"
    assert managed.metadata.update_count == update_count


def test_full_reconfiguration_discards_the_snapshot(snapshot_data, mocker):
    snapshot_data.snapshot_attribute("x")
    replacement = mocker.Mock(return_value="replacement")
    snapshot_data.create_or_reconfigure_attribute("x", replacement, initial_value="seed")

    snapshot_data.restore_attribute("x")
    assert snapshot_data._managed["x"].update_function is replacement


def test_raises_for_unknown_attribute(snapshot_data):
    with pytest.raises(AttributeError):
        snapshot_data.snapshot_attribute("unknown")
    with pytest.raises(AttributeError):
        snapshot_data.restore_attribute("unknown")
