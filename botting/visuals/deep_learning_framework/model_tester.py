import cv2
import os
from ultralytics import YOLO
from botting.utilities import take_screenshot
from paths import ROOT

# Define the path to the saved model
TRAINING_PROJECT_ROOT = "data/model_runs/character_detection"
NAME = "ClericChronosTraining - Nano120"
MODEL_PATH = os.path.join(ROOT, TRAINING_PROJECT_ROOT, NAME, "weights", "best.pt")

# Load the model
model = YOLO(MODEL_PATH, task="detect")

while True:
    img = take_screenshot(0x00850A0A)
    results = model(img)
    for res in results:
        for box in res.boxes:
            x1, y1, x2, y2 = box.xyxy.numpy().astype(int).squeeze()
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cls = box.cls.numpy()[0]
            conf = box.conf.numpy()[0]
            label = f"{cls} {conf:.3f}"
            cv2.putText(
                img,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (36, 255, 12),
                2,
            )
    cv2.imshow("img", img)
    cv2.waitKey(1)
