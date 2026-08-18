"""
Dataset annotation viewer.

Browse training images and visualize their YOLO format annotations.
Helps spot labeling errors and class imbalances.

Usage:
  python toolkit/inspect_dataset.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QFileDialog
)


class DatasetInspector(QMainWindow):
    """Browse and visualize dataset annotations."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dataset Annotation Inspector")
        self.setGeometry(100, 100, 1400, 900)

        self.image_files = []
        self.class_names = {}
        self.current_idx = 0
        self.dataset_root = None
        self.images_dir = None

        self._build_ui()
        self._load_dataset()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Dataset selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItems([
            "GS2MobsAndChar",
            "ChronosAndMp3WithCharacter",
            "Bubbling_final",
            "PacPinky_final",
        ])
        self.dataset_combo.currentTextChanged.connect(self._load_dataset)
        selector_layout.addWidget(self.dataset_combo)
        selector_layout.addStretch()

        open_btn = QPushButton("Browse Folder…")
        open_btn.clicked.connect(self._browse_folder)
        selector_layout.addWidget(open_btn)

        layout.addLayout(selector_layout)

        # Image display
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet("background-color: #222; color: #ccc;")
        self.canvas.setMinimumHeight(650)
        layout.addWidget(self.canvas, stretch=1)

        # Info
        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        # Navigation
        nav_layout = QHBoxLayout()
        self.idx_spin = QSpinBox()
        self.idx_spin.setRange(0, 0)
        self.idx_spin.valueChanged.connect(self._on_index_changed)
        nav_layout.addWidget(QLabel("Image:"))
        nav_layout.addWidget(self.idx_spin)

        prev_btn = QPushButton("← Prev")
        prev_btn.clicked.connect(self._prev_image)
        nav_layout.addWidget(prev_btn)

        next_btn = QPushButton("Next →")
        next_btn.clicked.connect(self._next_image)
        nav_layout.addWidget(next_btn)

        nav_layout.addStretch()

        self.stats_label = QLabel()
        nav_layout.addWidget(self.stats_label)

        layout.addLayout(nav_layout)

    def _load_dataset(self) -> None:
        dataset_name = self.dataset_combo.currentText()
        self.dataset_root = Path(f"data/datasets/{dataset_name}")

        if not self.dataset_root.exists():
            self.info_label.setText(f"Dataset not found: {self.dataset_root}")
            self.image_files = []
            return

        self.images_dir = self.dataset_root / "images"
        if not self.images_dir.exists():
            self.info_label.setText(f"No images/ folder in {self.dataset_root}")
            self.image_files = []
            return

        # Collect images from images/{train,val,test}/ (standard nested structure)
        # Also support flat structure for backward compat
        nested_images = sorted(self.images_dir.glob("*/*.jpg")) + sorted(self.images_dir.glob("*/*.png"))
        flat_images = sorted(self.images_dir.glob("*.jpg")) + sorted(self.images_dir.glob("*.png"))
        self.image_files = nested_images if nested_images else flat_images

        # Load class names from data.yaml if present
        yaml_path = None
        if (self.dataset_root / "data.yaml").exists():
            yaml_path = self.dataset_root / "data.yaml"
        elif (self.dataset_root.parent / "data.yaml").exists():
            yaml_path = self.dataset_root.parent / "data.yaml"

        self.class_names = {}
        if yaml_path:
            import yaml
            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)
                    if "names" in data:
                        names = data["names"]
                        if isinstance(names, list):
                            self.class_names = {i: name for i, name in enumerate(names)}
                        else:
                            self.class_names = names
            except Exception:
                pass

        self.idx_spin.setRange(0, max(0, len(self.image_files) - 1))
        self.current_idx = 0
        self._display_image()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder")
        if folder:
            self.dataset_root = None
            self.images_dir = None
            self.image_files = sorted(Path(folder).glob("*.jpg")) + sorted(Path(folder).glob("*.png"))
            self.idx_spin.setRange(0, max(0, len(self.image_files) - 1))
            self.current_idx = 0
            self._display_image()

    def _prev_image(self) -> None:
        self.current_idx = max(0, self.current_idx - 1)
        self.idx_spin.blockSignals(True)
        self.idx_spin.setValue(self.current_idx)
        self.idx_spin.blockSignals(False)
        self._display_image()

    def _next_image(self) -> None:
        self.current_idx = min(len(self.image_files) - 1, self.current_idx + 1)
        self.idx_spin.blockSignals(True)
        self.idx_spin.setValue(self.current_idx)
        self.idx_spin.blockSignals(False)
        self._display_image()

    def _on_index_changed(self, idx: int) -> None:
        self.current_idx = idx
        self._display_image()

    def _display_image(self) -> None:
        if not self.image_files:
            self.info_label.setText("No images loaded.")
            return

        img_path = self.image_files[self.current_idx]
        img = cv2.imread(str(img_path))
        if img is None:
            self.info_label.setText(f"Failed to load: {img_path.name}")
            return

        h, w = img.shape[:2]

        # Load and draw labels (handle both flat and nested structure)
        # If image is at images/char.jpg, look for labels/char.txt
        # If image is at images/train/char.jpg, look for labels/train/char.txt
        if self.images_dir and img_path.is_relative_to(self.images_dir):
            rel = img_path.relative_to(self.images_dir)
            label_path = self.dataset_root / "labels" / rel.with_suffix(".txt")
        else:
            # Browsed folder: try sibling labels/ dir, then same directory
            label_path = img_path.parent.parent / "labels" / f"{img_path.stem}.txt"
            if not label_path.exists():
                label_path = img_path.parent / f"{img_path.stem}.txt"

        detections = []
        if label_path.exists():
            with open(label_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        class_id = int(parts[0])
                        x_center, y_center, box_w, box_h = map(float, parts[1:5])
                        detections.append((class_id, x_center, y_center, box_w, box_h))

        # Draw bboxes
        for class_id, x_c, y_c, box_w, box_h in detections:
            x1 = int((x_c - box_w / 2) * w)
            y1 = int((y_c - box_h / 2) * h)
            x2 = int((x_c + box_w / 2) * w)
            y2 = int((y_c + box_h / 2) * h)

            class_name = self.class_names.get(class_id, f"Class {class_id}")
            color = (0, 255, 0) if class_name == "Character" else (255, 100, 0)

            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img, class_name, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )

        # Display
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)

        # Scale to fit canvas, maintaining aspect ratio, capped at 90% of canvas size
        if self.canvas.width() > 0 and self.canvas.height() > 0:
            max_width = int(self.canvas.width() * 0.9)
            max_height = int(self.canvas.height() * 0.9)
            scaled_pixmap = pixmap.scaled(
                max_width, max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            scaled_pixmap = pixmap.scaledToWidth(800, Qt.TransformationMode.SmoothTransformation)
        self.canvas.setPixmap(scaled_pixmap)

        # Stats
        self.info_label.setText(
            f"{img_path.name} — {w}×{h} — {len(detections)} detections"
        )
        self.stats_label.setText(
            f"{self.current_idx + 1} / {len(self.image_files)}"
        )


def main():
    app = QApplication(sys.argv)
    inspector = DatasetInspector()
    inspector.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
