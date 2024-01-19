import cv2
import json
import numpy as np
import os

from paths import ROOT
from royals.interface.fixed_components.in_game_chat.chat_lines import General

OUTPUT_FILENAME = "general_characters.json"
result = {}

with open(
        os.path.join(ROOT, 'tests/chat_lines.json'),
        'r'
) as fp:
    annotations = json.load(fp)


for idx, img_path in enumerate(os.listdir(os.path.join(ROOT, "tests", "images"))):
    if img_path.startswith('test'):
        continue
    elif annotations[img_path][0] != "General":
        continue

    full_path = os.path.join(ROOT, "tests", "images", img_path)
    img = cv2.imread(full_path)
    processed = General._preprocess_img(img)
    print(img_path)
    cv2.imshow('processed', cv2.resize(processed, None, fx=5, fy=5))
    cv2.waitKey(0)

    # Extract each contour. If contours are vertically aligned, they are grouped together
    # contours, _ = cv2.findContours(
    #     processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    # )
    #
    # # Group contours together if they are vertically aligned
    # grouped_contours = []
    # for contour in contours:
    #     if len(grouped_contours) == 0:
    #         grouped_contours.append([contour])
    #     else:
    #         for group in grouped_contours:
    #             if abs(cv2.boundingRect(contour)[0] - cv2.boundingRect(group[0])[0]) < 1:
    #                 group.append(contour)
    #                 break
    #         else:
    #             grouped_contours.append([contour])
    # rects = [cv2.boundingRect(np.vstack(group)) for group in grouped_contours]
    #
    # # # Extract each rect from the image and annotate it
    # for id_rect, rect in enumerate(rects):
    #     x, y, w, h = rect
    #     char = processed[y:y + h, x:x + w]
    #
    #     cv2.imshow('character', cv2.resize(char, None, fx=10, fy=10))
    #     cv2.waitKey(1)
    #     characters = input("Enter character observed")
    #     if characters == '':
    #         continue
    #     char_filename = f'{img_path.removesuffix(".png")}_{id_rect}'
    #     cv2.imwrite(os.path.join(
    #         ROOT, 'royals/assets/detection_characters', char_filename ),
    #         char
    #     )
    #     if result.get(char) is None:
    #         result[char] = [char_filename]
    #     else:
    #         result[char].append(char_filename)


    # results[os.path.basename(new_path)] = [line_type, line_text]


with open(os.path.join(ROOT, 'royals/assets/detection_characters', OUTPUT_FILENAME), 'w') as fp:
    json.dump(result, fp, indent=4)
