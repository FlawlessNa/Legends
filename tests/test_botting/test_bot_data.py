import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

from botting.core.bot_data import BotData, ManagedAttribute


class TestBotData(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")
        self.mock_update_function = Mock(return_value="new_value")

    def create_attribute(self, name, update_function, threshold=None):
        self.bot_data.create_attribute(name, update_function, threshold)

    def test_create_attribute_initializes_metadata(self):
        self.create_attribute("test_attr", self.mock_update_function)
        self.assertIn("test_attr", self.bot_data._metadata)
        self.assertEqual(self.bot_data._metadata["test_attr"].update_count, 1)

    def test_create_attribute_sets_initial_value(self):
        self.create_attribute("test_attr", self.mock_update_function)
        self.assertEqual(self.bot_data.test_attr, "new_value")

    def test_update_attribute_updates_value_and_metadata(self):
        self.create_attribute("test_attr", self.mock_update_function)
        self.assertEqual(self.bot_data.test_attr, "new_value")
        self.mock_update_function.return_value = "updated_value"
        self.bot_data.update_attribute("test_attr")
        self.assertEqual(self.bot_data.test_attr, "updated_value")
        self.assertEqual(self.bot_data._metadata["test_attr"].update_count, 2)

    def test_getattr_increments_access_count(self):
        self.create_attribute("test_attr", self.mock_update_function)
        _ = self.bot_data.test_attr
        self.assertEqual(self.bot_data._metadata["test_attr"].access_count, 1)

    def test_getattr_updates_value_if_threshold_exceeded(self):
        self.create_attribute("test_attr", self.mock_update_function, threshold=0.1)
        self.bot_data._managed["test_attr"].metadata.last_update_time = (
            datetime.now() - timedelta(seconds=0.2)
        )
        self.mock_update_function.return_value = "threshold_updated_value"
        _ = self.bot_data.test_attr
        self.assertEqual(self.bot_data.test_attr, "threshold_updated_value")

    def test_setattr_updates_metadata(self):
        self.create_attribute("test_attr", self.mock_update_function)
        self.bot_data.test_attr = "manually_set_value"
        self.assertEqual(self.bot_data.test_attr, "manually_set_value")
        self.assertIn(
            "manually_set_value", self.bot_data._metadata["test_attr"].prev_values
        )

    def test_update_attribute_raises_error_if_no_update_function(self):
        with self.assertRaises(AttributeError):
            self.bot_data.update_attribute("non_existent_attr")

    def test_create_attribute_with_threshold(self):
        self.create_attribute("test_attr", self.mock_update_function, threshold=1.0)
        self.assertIn("test_attr", self.bot_data._thresholds)
        self.assertEqual(self.bot_data._thresholds["test_attr"], 1.0)


class TestManagedAttribute(unittest.TestCase):
    """Tests for the ManagedAttribute encapsulation."""

    def setUp(self):
        self.bot_data = BotData("TestBot")
        self.mock_fn = Mock(return_value="value")

    def test_managed_attribute_created(self):
        self.bot_data.create_attribute("x", self.mock_fn)
        self.assertIn("x", self.bot_data._managed)
        managed = self.bot_data._managed["x"]
        self.assertEqual(managed.name, "x")
        self.assertEqual(managed.value, "value")

    def test_managed_attribute_encapsulates_threshold(self):
        self.bot_data.create_attribute("x", self.mock_fn, threshold=0.5)
        self.assertEqual(self.bot_data._managed["x"].threshold, 0.5)

    def test_managed_attribute_encapsulates_error_handler(self):
        handler = Mock()
        self.bot_data.create_attribute("x", self.mock_fn, error_handler=handler)
        self.assertIs(self.bot_data._managed["x"].error_handler, handler)

    def test_overwrite_preserves_metadata_history(self):
        self.bot_data.create_attribute("x", self.mock_fn)
        original_metadata = self.bot_data._managed["x"].metadata
        self.mock_fn.return_value = "new_value"
        self.bot_data.create_attribute("x", self.mock_fn, threshold=1.0)
        self.assertIs(self.bot_data._managed["x"].metadata, original_metadata)

    def test_overwrite_updates_function_and_threshold(self):
        self.bot_data.create_attribute("x", self.mock_fn, threshold=0.5)
        new_fn = Mock(return_value="updated")
        self.bot_data.create_attribute("x", new_fn, threshold=2.0)
        self.assertIs(self.bot_data._managed["x"].update_function, new_fn)
        self.assertEqual(self.bot_data._managed["x"].threshold, 2.0)


class TestHasPrefix(unittest.TestCase):
    """Tests for the has_* prefix feature-flag behavior."""

    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_unregistered_has_returns_false(self):
        self.assertFalse(self.bot_data.has_minimap_attributes)
        self.assertFalse(self.bot_data.has_smart_rotation)
        self.assertFalse(self.bot_data.has_rotation_attributes)

    def test_registered_has_returns_value(self):
        self.bot_data.create_attribute("has_minimap_attributes", lambda: True)
        self.assertTrue(self.bot_data.has_minimap_attributes)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling in attribute updates."""

    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_error_handler_called_on_failure(self):
        calls = []

        def failing_then_ok():
            calls.append(1)
            if len(calls) <= 1:
                raise ValueError("fail")
            return "ok"

        handler = Mock()
        self.bot_data.create_attribute("x", failing_then_ok, error_handler=handler)
        self.assertEqual(self.bot_data.x, "ok")
        handler.assert_called_once()

    def test_error_raised_without_handler(self):
        self.bot_data.create_attribute("x", lambda: 1)
        self.bot_data._managed["x"].update_function = Mock(
            side_effect=ValueError("fail")
        )
        with self.assertRaises(ValueError):
            self.bot_data.update_attribute("x")


class TestAttributeAccess(unittest.TestCase):
    """Tests for attribute access and setting behaviors."""

    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_setattr_on_unknown_raises(self):
        with self.assertRaises(AttributeError):
            self.bot_data.unknown = "value"

    def test_getattr_on_unknown_raises(self):
        with self.assertRaises(AttributeError):
            _ = self.bot_data.unknown

    def test_ign_is_normal_attribute(self):
        self.assertEqual(self.bot_data.ign, "TestBot")
        self.bot_data.ign = "NewBot"
        self.assertEqual(self.bot_data.ign, "NewBot")

    def test_initial_value_bypasses_update(self):
        fn = Mock(return_value="should_not_be_used")
        self.bot_data.create_attribute("x", fn, initial_value="preset")
        self.assertEqual(self.bot_data._managed["x"].value, "preset")
        fn.assert_not_called()

    def test_falsy_initial_value_bypasses_update(self):
        fn = Mock(return_value="should_not_be_used")
        self.bot_data.create_attribute("x", fn, initial_value=False)
        self.assertEqual(self.bot_data._managed["x"].value, False)
        fn.assert_not_called()

    def test_get_time_since_last_valid_update(self):
        self.bot_data.create_attribute("x", lambda: "valid")
        elapsed = self.bot_data.get_time_since_last_valid_update("x")
        self.assertGreaterEqual(elapsed, 0)
        self.assertLess(elapsed, 1)

    def test_get_time_since_last_valid_update_raises_for_unknown(self):
        with self.assertRaises(AttributeError):
            self.bot_data.get_time_since_last_valid_update("unknown")

    def test_get_time_since_last_value_change(self):
        self.bot_data.create_attribute("x", lambda: "val")
        elapsed = self.bot_data.get_time_since_last_value_change("x")
        self.assertGreaterEqual(elapsed, 0)
        self.assertLess(elapsed, 1)

    def test_get_time_since_last_value_change_raises_for_unknown(self):
        with self.assertRaises(AttributeError):
            self.bot_data.get_time_since_last_value_change("unknown")

    def test_check_if_values_have_changed_false_for_static(self):
        self.bot_data.create_attribute("x", lambda: 42)
        for _ in range(5):
            self.bot_data.update_attribute("x")
        self.assertFalse(self.bot_data.check_if_values_have_changed("x"))

    def test_check_if_values_have_changed_true_for_changing(self):
        counter = [0]
        self.bot_data.create_attribute(
            "x", lambda: (counter.__setitem__(0, counter[0] + 1), counter[0])[1]
        )
        for _ in range(3):
            self.bot_data.update_attribute("x")
        self.assertTrue(self.bot_data.check_if_values_have_changed("x"))


if __name__ == "__main__":
    unittest.main()
