import cv2
import json
import os

from unittest import TestCase

from royals.model.interface.fixed_components.in_game_chat.chat_lines import ChatLine
from paths import ROOT


class TestChatLines(TestCase):
    def setUp(self) -> None:
        self.img_path = os.path.join(ROOT, "tests", "images")
        self.all_files = (
            file for file in os.listdir(self.img_path) if file.startswith("line_test")
        )
        with open(os.path.join(ROOT, "tests", "chat_lines.json"), "r") as f:
            self.expected = json.load(f)

    def test_from_img(self):
        for file in self.all_files:
            full_path = os.path.join(self.img_path, file)
            img = cv2.imread(full_path)
            chat_line = ChatLine.from_img(img)
            self.assertEqual(chat_line.name, self.expected[file][0])

    def test_read_text(self):
        for file in self.all_files:
            full_path = os.path.join(self.img_path, file)
            img = cv2.imread(full_path)

            if self.expected[file][0] in [
                "General",
                # 'Whisper',
                # 'GM',
                # 'Notice',
                # 'System',
                # 'Warning'
            ]:
                chat_line = ChatLine.from_img(img, read=True)

        self.assertEqual(chat_line.text, self.expected[file][1])
