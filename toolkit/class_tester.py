import os
import cv2
import numpy as np

from botting.utilities import take_screenshot
from royals.models_implementations import RoyalsData
from paths import ROOT
from royals.models_implementations.characters import Magician


HANDLE = 0x02300A26


if __name__ == "__main__":
    while True:
        img = take_screenshot(HANDLE)
        processed = cv2.inRange(img, (68, 68, 51), (68, 68, 51))
        contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # for cnt in contours:
        #     x, y, w, h = cv2.boundingRect(cnt)
        #     cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        rects = [cv2.boundingRect(cnt) for cnt in contours if 10 <= cv2.contourArea(cnt) <= 90]
        areas = [cv2.contourArea(cnt) for cnt in contours if 10 <= cv2.contourArea(cnt) <= 90]
        grouped = cv2.groupRectangles(rects, 1, 2)
        for x, y, w, h in grouped[0]:
        # for x, y, w, h in rects:
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow('img', img)
        cv2.waitKey(1)
        print(np.count_nonzero(processed))