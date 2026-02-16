import cv2
import os
from ultralytics import YOLO
from botting.utilities import take_screenshot
from paths import ROOT

# Define the path to the saved model
TRAINING_PROJECT_ROOT = "data/model_runs/detection"
NAME = "Full Model up to GS2 - Nano"
MODEL_PATH = os.path.join(ROOT, TRAINING_PROJECT_ROOT, NAME, "weights", "best.pt")

# Load the model
model = YOLO(MODEL_PATH, task="detect")
i = 0
total_time = 0
import time
while True:
    img = take_screenshot(0x01290906)
    start = time.time()
    results = model(img)
    total_time += time.time() - start
    i += 1

    for res in results:
        cv2.imshow('Predictions', res.plot())
        cv2.waitKey(1)
    print(i)
    # if i == 1000:
    #     break
print('avg time', total_time / i)