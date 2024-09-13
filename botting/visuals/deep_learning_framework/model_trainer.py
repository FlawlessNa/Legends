import os
from ultralytics import YOLO
from paths import ROOT

PRETRAINED_MODEL_PATH = 'yolov8n.pt'
PATH_TO_DATA = 'data/character_detection_images/ChronosClericTraining/data.yaml'  # yaml file
TRAINING_PROJECT_ROOT = 'data/model_runs/character_detection'
NAME = 'ClericChronosTraining - Nano'

model = YOLO(PRETRAINED_MODEL_PATH, task='detect')
result = model.train(
    data=os.path.join(ROOT, PATH_TO_DATA),
    epochs=120,
    imgsz=640,
    project=os.path.join(ROOT, TRAINING_PROJECT_ROOT),
    name=NAME,
    exists_ok=True
)
breakpoint()