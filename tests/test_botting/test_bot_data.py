import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

from botting.core.botv2.bot_data import BotData, AttributeMetadata


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
        self.bot_data._metadata["test_attr"].last_update_time = (
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
            "manually_set_value", self.bot_data._metadata["test_attr"].last_values
        )

    def test_update_attribute_raises_error_if_no_update_function(self):
        with self.assertRaises(AttributeError):
            self.bot_data.update_attribute("non_existent_attr")

    def test_create_attribute_with_threshold(self):
        self.create_attribute("test_attr", self.mock_update_function, threshold=1.0)
        self.assertIn("test_attr", self.bot_data._thresholds)
        self.assertEqual(self.bot_data._thresholds["test_attr"], 1.0)


if __name__ == "__main__":
    unittest.main()