"""
Live object detection viewer.

Continuously captures the game window and runs YOLO inference on each frame.
Adjust confidence and IOU thresholds live using the sliders.

Usage:
  python toolkit/live_detector.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_training.gui.live_inference import run_live_inference

# ── Configuration ──────────────────────────────────────────────────────────

# Path to the YOLO model file (.pt)
MODEL_PATH = "data/models/production/global/weights/best.pt"

# Classes to display (should match model's classes)
CLASSES = ["Character", "Bubbling"]

# Initial thresholds (adjust with sliders)
INITIAL_CONF = 0.35
INITIAL_IOU = 0.45

# ───────────────────────────────────────────────────────────────────────────


def main():
    try:
        import win32gui

        from maple.screen.client import find_client
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Make sure botting module is available in the repo.")
        sys.exit(1)

    # Check model exists
    if not Path(MODEL_PATH).exists():
        print(f"ERROR: Model not found at {MODEL_PATH}")
        print("Update MODEL_PATH to point to a valid .pt file.")
        sys.exit(1)

    # Get game window handle
    handle = find_client()
    title = win32gui.GetWindowText(handle)
    print(f"Found game window: '{title}' (handle {handle})")
    print(f"Loading model: {MODEL_PATH}")
    print()

    # Run the live inference viewer
    try:
        conf, iou = run_live_inference(
            model_path=MODEL_PATH,
            window_handle=handle,
            classes=CLASSES,
            conf=INITIAL_CONF,
            iou=INITIAL_IOU,
        )
        print(f"\nFinal thresholds: conf={conf:.2f}, iou={iou:.2f}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
