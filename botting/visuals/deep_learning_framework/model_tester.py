import cv2
import os
from ultralytics import YOLO
from botting.utilities import take_screenshot
from paths import ROOT

# Define the path to the saved model
TRAINING_PROJECT_ROOT = "data/model_runs/character_detection"
NAME = "ChronosAndMp3WithCharacter - Nano"
MODEL_PATH = os.path.join(ROOT, TRAINING_PROJECT_ROOT, NAME, "weights", "best.pt")

# Load the model
model = YOLO(MODEL_PATH, task="detect")
while True:
    img = take_screenshot(0x004B0DE2)
    results = model(img)
    for res in results:
        cv2.imshow('Predictions', res.plot())
        cv2.waitKey(1)
