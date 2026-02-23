import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

from botting.core.bot_data import BotData, ManagedAttribute, _SENTINEL


class TestCreateAttribute(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")
        self.mock_fn = Mock(return_value="new_value")

    def test_initializes_metadata(self):
        self.bot_data.create_attribute("test_attr", self.mock_fn)
        self.assertIn("test_attr", self.bot_data._managed)
        self.assertEqual(self.bot_data._managed["test_attr"].metadata.update_count, 1)

    def test_sets_initial_value_via_update(self):
        self.bot_data.create_attribute("test_attr", self.mock_fn)
        self.assertEqual(self.bot_data.test_attr, "new_value")

    def test_with_explicit_initial_value(self):
        fn = Mock(return_value="should_not_be_used")
        self.bot_data.create_attribute("x", fn, initial_value="preset")
        self.assertEqual(self.bot_data._managed["x"].value, "preset")
        fn.assert_not_called()

    def test_falsy_initial_value_bypasses_update(self):
        fn = Mock(return_value="should_not_be_used")
        self.bot_data.create_attribute("x", fn, initial_value=False)
        self.assertEqual(self.bot_data._managed["x"].value, False)
        fn.assert_not_called()

    def test_raises_if_already_exists(self):
        self.bot_data.create_attribute("x", self.mock_fn)
        with self.assertRaises(AttributeError):
            self.bot_data.create_attribute("x", self.mock_fn)

    def test_with_threshold(self):
        self.bot_data.create_attribute("x", self.mock_fn, threshold=1.0)
        self.assertEqual(self.bot_data._managed["x"].threshold, 1.0)


class TestReconfigureAttribute(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")
        self.mock_fn = Mock(return_value="value")

    def test_preserves_metadata_history(self):
        self.bot_data.create_attribute("x", self.mock_fn)
        original_metadata = self.bot_data._managed["x"].metadata
        new_fn = Mock(return_value="updated")
        self.bot_data.reconfigure_attribute("x", update_function=new_fn, threshold=1.0)
        self.assertIs(self.bot_data._managed["x"].metadata, original_metadata)

    def test_updates_function_and_threshold(self):
        self.bot_data.create_attribute("x", self.mock_fn, threshold=0.5)
        new_fn = Mock(return_value="updated")
        self.bot_data.reconfigure_attribute("x", update_function=new_fn, threshold=2.0)
        self.assertIs(self.bot_data._managed["x"].update_function, new_fn)
        self.assertEqual(self.bot_data._managed["x"].threshold, 2.0)

    def test_can_set_error_handler_to_none(self):
        handler = Mock()
        self.bot_data.create_attribute(
            "x", Mock(return_value=1), error_handler=handler
        )
        self.bot_data.reconfigure_attribute("x", error_handler=None)
        self.assertIsNone(self.bot_data._managed["x"].error_handler)

    def test_leaves_unspecified_fields_unchanged(self):
        self.bot_data.create_attribute("x", self.mock_fn, threshold=0.5)
        self.bot_data.reconfigure_attribute("x", threshold=2.0)
        # update_function should be unchanged
        self.assertIs(self.bot_data._managed["x"].update_function, self.mock_fn)
        self.assertEqual(self.bot_data._managed["x"].threshold, 2.0)

    def test_raises_for_unknown(self):
        with self.assertRaises(AttributeError):
            self.bot_data.reconfigure_attribute(
                "nonexistent", update_function=lambda: 1
            )


class TestCreateOrReconfigureAttribute(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")
        self.mock_fn = Mock(return_value="value")

    def test_creates_when_new(self):
        self.bot_data.create_or_reconfigure_attribute("x", self.mock_fn)
        self.assertIn("x", self.bot_data._managed)
        self.assertEqual(self.bot_data.x, "value")

    def test_reconfigures_when_existing(self):
        self.bot_data.create_attribute("x", self.mock_fn)
        original_metadata = self.bot_data._managed["x"].metadata
        new_fn = Mock(return_value="updated")
        self.bot_data.create_or_reconfigure_attribute("x", new_fn, threshold=1.0)
        self.assertIs(self.bot_data._managed["x"].metadata, original_metadata)
        self.assertIs(self.bot_data._managed["x"].update_function, new_fn)
        self.assertEqual(self.bot_data._managed["x"].threshold, 1.0)

    def test_promotes_static_to_managed(self):
        self.bot_data.set_static("x", "static_val")
        self.bot_data.create_or_reconfigure_attribute("x", self.mock_fn)
        self.assertNotIn("x", self.bot_data._static)
        self.assertIn("x", self.bot_data._managed)
        self.assertEqual(self.bot_data.x, "value")

    def test_create_attribute_promotes_static(self):
        self.bot_data.set_static("x", "static_val")
        self.bot_data.create_attribute("x", self.mock_fn)
        self.assertNotIn("x", self.bot_data._static)
        self.assertIn("x", self.bot_data._managed)
        self.assertEqual(self.bot_data.x, "value")


class TestStaticAttributes(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_set_and_get_static(self):
        self.bot_data.set_static("handle", 12345)
        self.assertEqual(self.bot_data.handle, 12345)

    def test_overwrite_static(self):
        self.bot_data.set_static("x", 1)
        self.bot_data.set_static("x", 2)
        self.assertEqual(self.bot_data.x, 2)

    def test_setattr_on_static(self):
        self.bot_data.set_static("x", 1)
        self.bot_data.x = 42
        self.assertEqual(self.bot_data.x, 42)

    def test_managed_takes_priority_over_static(self):
        mock_fn = Mock(return_value="managed_val")
        self.bot_data.create_attribute("x", mock_fn)
        self.bot_data._static["x"] = "static_val"
        self.assertEqual(self.bot_data.x, "managed_val")


class TestFeatureFlags(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_unregistered_has_returns_false(self):
        self.assertFalse(self.bot_data.has_minimap_attributes)
        self.assertFalse(self.bot_data.has_smart_rotation)
        self.assertFalse(self.bot_data.has_rotation_attributes)

    def test_set_feature(self):
        self.bot_data.set_feature("has_minimap_attributes")
        self.assertTrue(self.bot_data.has_minimap_attributes)

    def test_remove_feature(self):
        self.bot_data.set_feature("has_minimap_attributes")
        self.bot_data.remove_feature("has_minimap_attributes")
        self.assertFalse(self.bot_data.has_minimap_attributes)

    def test_remove_nonexistent_feature_is_safe(self):
        self.bot_data.remove_feature("has_nonexistent")  # should not raise


class TestErrorHandling(unittest.TestCase):
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

    def test_max_retries_caps_recursion(self):
        """Error handler that never fixes the problem stops after max_retries."""
        fn = Mock(side_effect=ValueError("always fails"))
        handler = Mock()
        self.bot_data.create_attribute("x", lambda: 1)
        self.bot_data._managed["x"].update_function = fn
        self.bot_data._managed["x"].error_handler = handler
        self.bot_data._managed["x"].max_retries = 2
        with self.assertRaises(ValueError):
            self.bot_data.update_attribute("x")
        self.assertEqual(handler.call_count, 2)

    def test_max_retries_default_is_one(self):
        fn = Mock(side_effect=ValueError("always fails"))
        handler = Mock()
        self.bot_data.create_attribute("x", lambda: 1)
        self.bot_data._managed["x"].update_function = fn
        self.bot_data._managed["x"].error_handler = handler
        with self.assertRaises(ValueError):
            self.bot_data.update_attribute("x")
        self.assertEqual(handler.call_count, 1)


class TestAttributeAccess(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")

    def test_getattr_auto_refreshes_on_threshold(self):
        mock_fn = Mock(return_value="initial")
        self.bot_data.create_attribute("x", mock_fn, threshold=0.1)
        self.bot_data._managed["x"].metadata.last_update_time = (
            datetime.now() - timedelta(seconds=0.2)
        )
        mock_fn.return_value = "refreshed"
        self.assertEqual(self.bot_data.x, "refreshed")

    def test_getattr_increments_access_count(self):
        mock_fn = Mock(return_value="val")
        self.bot_data.create_attribute("x", mock_fn)
        _ = self.bot_data.x
        self.assertEqual(self.bot_data._managed["x"].metadata.access_count, 1)

    def test_setattr_on_managed(self):
        mock_fn = Mock(return_value="val")
        self.bot_data.create_attribute("x", mock_fn)
        self.bot_data.x = "manual"
        self.assertEqual(self.bot_data.x, "manual")
        self.assertIn("manual", self.bot_data._managed["x"].metadata.prev_values)

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

    def test_update_attribute_updates_value(self):
        mock_fn = Mock(return_value="initial")
        self.bot_data.create_attribute("x", mock_fn)
        mock_fn.return_value = "updated"
        self.bot_data.update_attribute("x")
        self.assertEqual(self.bot_data.x, "updated")
        self.assertEqual(self.bot_data._managed["x"].metadata.update_count, 2)

    def test_update_attribute_raises_for_unknown(self):
        with self.assertRaises(AttributeError):
            self.bot_data.update_attribute("nonexistent")


class TestQueryMethods(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData("TestBot")

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

    def test_check_if_values_have_changed_raises_for_unknown(self):
        with self.assertRaises(AttributeError):
            self.bot_data.check_if_values_have_changed("unknown")


if __name__ == "__main__":
    unittest.main()
