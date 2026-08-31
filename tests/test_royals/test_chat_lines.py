import cv2
import json
import os

import pytest

from maple.model.interface.fixed_components.in_game_chat.chat_lines import ChatLine
from paths import ROOT


@pytest.fixture
def img_path() -> str:
    return os.path.join(ROOT, "tests", "images")


@pytest.fixture
def all_files(img_path):
    # A generator, deliberately: each test gets a fresh one and consumes it once.
    return (file for file in os.listdir(img_path) if file.startswith("line_test"))


@pytest.fixture
def expected() -> dict:
    with open(os.path.join(ROOT, "tests", "chat_lines.json"), "r") as f:
        return json.load(f)


def test_from_img(img_path, all_files, expected):
    for file in all_files:
        full_path = os.path.join(img_path, file)
        img = cv2.imread(full_path)
        chat_line = ChatLine.from_img(img)
        assert chat_line.name == expected[file][0]


@pytest.mark.xfail(
    reason="Asserts the installed Tesseract build's OCR output, so it is "
    "machine-dependent; also asserts outside its loop. See issue #89.",
    strict=False,
)
def test_read_text(img_path, all_files, expected):
    for file in all_files:
        full_path = os.path.join(img_path, file)
        img = cv2.imread(full_path)

        if expected[file][0] in [
            "General",
            # 'Whisper',
            # 'GM',
            # 'Notice',
            # 'System',
            # 'Warning'
        ]:
            chat_line = ChatLine.from_img(img, read=True)

    assert chat_line.text == expected[file][1]
