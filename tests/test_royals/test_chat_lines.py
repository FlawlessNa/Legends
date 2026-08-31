import json
import os
from collections.abc import Iterator

import cv2
import pytest

from maple.model.interface.fixed_components.in_game_chat.chat_lines import ChatLine
from paths import ROOT


@pytest.fixture
def img_path() -> str:
    return os.path.join(ROOT, "tests", "images")


@pytest.fixture
def all_files(img_path: str) -> Iterator[str]:
    # A generator, deliberately: each test gets a fresh one and consumes it once.
    return (file for file in os.listdir(img_path) if file.startswith("line_test"))


@pytest.fixture
def expected() -> dict:
    with open(os.path.join(ROOT, "tests", "chat_lines.json"), "r") as f:
        return json.load(f)


def test_from_img(img_path: str, all_files: Iterator[str], expected: dict) -> None:
    for file in all_files:
        full_path = os.path.join(img_path, file)
        img = cv2.imread(full_path)
        assert img is not None, f"Failed to load image {full_path}"
        chat_line = ChatLine.from_img(img)
        assert chat_line.name == expected[file][0]
