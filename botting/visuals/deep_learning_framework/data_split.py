"""
Use this script to split the data, which may have been exported into a single .txt file
if CVAT annotator was used. Additionally, formats the folder structure to be compatible
with the YOLOv8 framework.
"""

import os
import random
from paths import ROOT

TRAIN_PROP = 0.7
VAL_PROP = 0.2
TEST_PROP = 0.1

# The images must be saved into the same path as where the ANNOTATOR OUTPUT is saved
ANNOTATOR_OUTPATH = os.path.join(
    ROOT, "data/character_detection_images/ChronosClericTraining"
)

# Make sure to Ctrl+R the paths within the txt files to the images folder
TRAIN_TXT_FILE = os.path.join(
    ROOT, "data/character_detection_images/ChronosClericTraining/train.txt"
)

with open(TRAIN_TXT_FILE, "r") as f:
    lines = f.readlines()

random.shuffle(lines)

total_lines = len(lines)
train_end = int(total_lines * TRAIN_PROP)
val_end = train_end + int(total_lines * VAL_PROP)


train_lines = lines[:train_end]
val_lines = lines[train_end:val_end]
test_lines = lines[val_end:]

for dtype in ["train", "val", "test"]:
    for ftype in ["images", "labels"]:
        os.makedirs(os.path.join(ANNOTATOR_OUTPATH, dtype, ftype))

for line in lines:
    full_path = os.path.join(ROOT, line.strip())
    label_path = full_path.replace("/images/", "/labels/train/").replace(".png", ".txt")
    if line in train_lines:
        new_path = os.path.join(
            ANNOTATOR_OUTPATH, "train", "images", os.path.basename(full_path)
        )
        new_label_path = os.path.join(
            ANNOTATOR_OUTPATH, "train", "labels", os.path.basename(label_path)
        )
    elif line in val_lines:
        new_path = os.path.join(
            ANNOTATOR_OUTPATH, "val", "images", os.path.basename(full_path)
        )
        new_label_path = os.path.join(
            ANNOTATOR_OUTPATH, "val", "labels", os.path.basename(label_path)
        )
    else:
        new_path = os.path.join(
            ANNOTATOR_OUTPATH, "test", "images", os.path.basename(full_path)
        )
        new_label_path = os.path.join(
            ANNOTATOR_OUTPATH, "test", "labels", os.path.basename(label_path)
        )
    os.rename(full_path, new_path)
    os.rename(label_path, new_label_path)

os.remove(TRAIN_TXT_FILE)
os.remove(os.path.dirname(full_path))
os.remove(os.path.dirname(label_path))
