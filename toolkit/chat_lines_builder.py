import cv2
import json
import os

from paths import ROOT
from royals.interface import LargeClientChatFeed
from royals.interface.fixed_components.in_game_chat.chat_lines import ChatLine

OUTPUT_FILENAME = "chat_lines.json"
feed = LargeClientChatFeed()

with open(os.path.join(ROOT, 'tests', OUTPUT_FILENAME), 'r') as fp:
    results = json.load(fp)


for idx, img_path in enumerate(os.listdir(os.path.join(ROOT, "tests", "images"))):
    if img_path.startswith('test'):
        continue

    full_path = os.path.join(ROOT, "tests", "images", img_path)
    new_path = os.path.join(ROOT, "tests", "images", f"line_test_{idx}.png")
    os.replace(full_path, new_path)
    img = cv2.imread(new_path)
    cv2.imshow('img', cv2.resize(img, None, fx=5, fy=5))
    cv2.waitKey(1)
    line_type = input("Enter Line Type")
    line_text = input("Enter Text")
    results[os.path.basename(new_path)] = [line_type, line_text]


with open(os.path.join(ROOT, 'tests', OUTPUT_FILENAME), 'w') as fp:
    json.dump(results, fp, indent=4)
