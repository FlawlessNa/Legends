"""PyQt6-based annotation and verification GUI."""

import sys
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QPoint, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import SUPPORTED_IMAGE_PATTERNS, config


class AnnotatorAborted(Exception):
    """Raised when the user aborts the annotation session."""


class BoundingBox:
    """Bounding box representation."""

    def __init__(
        self, x1: int, y1: int, x2: int, y2: int, class_id: int, confidence: float = 1.0
    ):
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.class_id = class_id
        self.confidence = confidence

    def to_yolo(self, img_width: int, img_height: int) -> str:
        x_center = ((self.x1 + self.x2) / 2) / img_width
        y_center = ((self.y1 + self.y2) / 2) / img_height
        width = (self.x2 - self.x1) / img_width
        height = (self.y2 - self.y1) / img_height
        return f"{self.class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"

    @classmethod
    def from_yolo(cls, line: str, img_width: int, img_height: int) -> BoundingBox:
        parts = line.strip().split()
        class_id = int(parts[0])
        x_center = float(parts[1]) * img_width
        y_center = float(parts[2]) * img_height
        width = float(parts[3]) * img_width
        height = float(parts[4]) * img_height
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        return cls(x1, y1, x2, y2, class_id)

    def contains_point(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class AnnotationCanvas(QLabel):
    """Canvas for drawing annotations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drawing = False
        self.start_point = None
        self.current_point = None
        self.temp_box = None

        self.scale_factor = 1.0

    def set_image(self, image: np.ndarray) -> None:
        self.original_image = image.copy()
        self.display_image()

    def resizeEvent(self, event) -> None:
        """Re-render at the new size whenever the canvas is resized."""
        super().resizeEvent(event)
        self.display_image()

    def display_image(self) -> None:
        if not hasattr(self, "original_image"):
            return

        # Guard: canvas has no real size yet (pre-show)
        if self.width() < 10 or self.height() < 10:
            return

        display_img = self.original_image.copy()

        for box in self.parent_window.boxes:
            color = self.parent_window.get_color(box.class_id)
            cv2.rectangle(display_img, (box.x1, box.y1), (box.x2, box.y2), color, 2)
            label = self.parent_window.classes[box.class_id]
            cv2.putText(
                display_img,
                label,
                (box.x1, box.y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )

        if self.temp_box:
            color = self.parent_window.get_color(self.parent_window.current_class)
            cv2.rectangle(
                display_img,
                (self.temp_box.x1, self.temp_box.y1),
                (self.temp_box.x2, self.temp_box.y2),
                color,
                2,
            )

        height, width, _ = display_img.shape
        q_image = QImage(
            display_img.data,
            width,
            height,
            3 * width,
            QImage.Format.Format_BGR888,
        )
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.scale_factor = scaled_pixmap.width() / width
        self.setPixmap(scaled_pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.get_image_coords(event.pos())
            if not pos:
                return
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.parent_window.remove_box_at(pos)
                return
            self.drawing = True
            self.start_point = pos

    def mouseMoveEvent(self, event):
        if self.drawing and self.start_point:
            pos = self.get_image_coords(event.pos())
            if pos:
                self.current_point = pos
                self.temp_box = BoundingBox(
                    self.start_point[0],
                    self.start_point[1],
                    pos[0],
                    pos[1],
                    self.parent_window.current_class,
                )
                self.display_image()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            pos = self.get_image_coords(event.pos())
            if (
                pos
                and self.start_point
                and (
                    abs(pos[0] - self.start_point[0]) > 5
                    and abs(pos[1] - self.start_point[1]) > 5
                )
            ):
                box = BoundingBox(
                    self.start_point[0],
                    self.start_point[1],
                    pos[0],
                    pos[1],
                    self.parent_window.current_class,
                )
                self.parent_window.add_box(box)
            self.drawing = False
            self.start_point = None
            self.current_point = None
            self.temp_box = None
            self.display_image()

    def get_image_coords(self, pos: QPoint) -> tuple[int, int] | None:
        if not self.pixmap():
            return None

        pixmap_rect = self.pixmap().rect()
        widget_rect = self.rect()

        x_offset = (widget_rect.width() - pixmap_rect.width()) // 2
        y_offset = (widget_rect.height() - pixmap_rect.height()) // 2

        x = int((pos.x() - x_offset) / self.scale_factor)
        y = int((pos.y() - y_offset) / self.scale_factor)

        if hasattr(self, "original_image"):
            h, w = self.original_image.shape[:2]
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            return (x, y)

        return None


class RetrainThread(QThread):
    """Background thread that runs the retrain computation without blocking the GUI."""

    finished = pyqtSignal(str)  # emits new model path (or "" on failure)

    def __init__(self, compute_fn, verified_count: int):
        super().__init__()
        self._fn = compute_fn
        self._verified_count = verified_count

    def run(self):
        try:
            result = self._fn(self._verified_count)
            self.finished.emit(result or "")
        except Exception:
            import traceback

            traceback.print_exc()
            self.finished.emit("")


class AnnotatorGUI(QMainWindow):
    """Annotation and verification GUI."""

    def __init__(
        self,
        images_dir: str,
        labels_dir: str,
        classes: list[str],
        mode: str = "annotate",
        retrain_every: int = 0,
        retrain_callback=None,
    ):
        super().__init__()

        self.images_dir = Path(images_dir)
        self.labels_dir = Path(labels_dir)
        self.labels_dir.mkdir(parents=True, exist_ok=True)

        self.classes = classes
        self.mode = mode
        self.aborted = False

        # Iterative retrain tracking
        # retrain_callback is kept for backward compat; preferred: retrain_compute_fn + retrain_post_fn
        self._retrain_every = retrain_every
        if retrain_callback is not None:
            # Legacy: wrap single callback as compute_fn, no post_fn
            self._retrain_compute_fn = retrain_callback
            self._retrain_post_fn = None
        else:
            self._retrain_compute_fn = None
            self._retrain_post_fn = None
        self._max_verified_index = (
            0  # high-watermark: highest index user has moved past
        )
        self._retrain_thread = None  # keep reference so GC doesn't collect it

        self.image_files = []
        for ext in SUPPORTED_IMAGE_PATTERNS:
            self.image_files.extend(list(self.images_dir.glob(ext)))
        self.image_files = sorted(self.image_files)

        if not self.image_files:
            QMessageBox.critical(None, "Error", f"No images found in {images_dir}")
            sys.exit(1)

        self.current_index = 0
        self.boxes: list[BoundingBox] = []
        self.current_class = 0

        self.init_ui()
        self.load_image(0)

    def init_ui(self) -> None:
        self.setWindowTitle(f"Annotator - {self.mode.capitalize()} Mode")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Info bar
        info_layout = QHBoxLayout()
        self.info_label = QLabel()
        info_layout.addWidget(self.info_label)
        main_layout.addLayout(info_layout)

        # Canvas
        self.canvas = AnnotationCanvas(self)
        main_layout.addWidget(self.canvas, stretch=1)

        # Controls
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.classes)
        self.class_combo.currentIndexChanged.connect(self.on_class_changed)
        controls_layout.addWidget(self.class_combo)

        self.prev_btn = QPushButton("Previous (A)")
        self.prev_btn.clicked.connect(self.prev_image)
        controls_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next (D)")
        self.next_btn.clicked.connect(self.next_image)
        controls_layout.addWidget(self.next_btn)

        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_labels)
        controls_layout.addWidget(self.save_btn)

        self.delete_btn = QPushButton("Delete Last Box (Del)")
        self.delete_btn.clicked.connect(self.delete_last_box)
        controls_layout.addWidget(self.delete_btn)

        controls_layout.addWidget(QLabel("Ctrl+Click box: remove"))

        if self.mode == "verify":
            self.accept_btn = QPushButton("Accept (Enter)")
            self.accept_btn.clicked.connect(self.accept_and_next)
            controls_layout.addWidget(self.accept_btn)
        else:
            self.next_btn.setText("Next (D / Enter)")

        # Abort button — visually separated with red styling
        controls_layout.addStretch()
        self.abort_btn = QPushButton("Abort Session")
        self.abort_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; "
            "padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        self.abort_btn.clicked.connect(self.abort_session)
        controls_layout.addWidget(self.abort_btn)

        main_layout.addLayout(controls_layout)

        # Keyboard shortcuts
        QShortcut(QKeySequence("A"), self).activated.connect(self.prev_image)
        QShortcut(QKeySequence("D"), self).activated.connect(self.next_image)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_labels)
        QShortcut(QKeySequence("Del"), self).activated.connect(self.delete_last_box)
        QShortcut(QKeySequence("Return"), self).activated.connect(
            self.accept_and_next if self.mode == "verify" else self.next_image
        )

    def update_info(self) -> None:
        is_last = self.current_index == len(self.image_files) - 1
        info = f"Image {self.current_index + 1}/{len(self.image_files)} | "
        info += f"Boxes: {len(self.boxes)} | "
        if is_last:
            info += "LAST IMAGE — press D or Enter to finish"
        else:
            info += f"File: {self.image_files[self.current_index].name}"
            if self._retrain_every > 0:
                next_retrain = self._retrain_every - (
                    self._max_verified_index % self._retrain_every
                )
                if next_retrain == self._retrain_every:
                    next_retrain = 0
                if next_retrain > 0:
                    info += f" | retrain in {next_retrain}"
        self.info_label.setText(info)

    def load_image(self, index: int) -> None:
        if not 0 <= index < len(self.image_files):
            return

        self.current_index = index
        image_path = self.image_files[index]

        image = cv2.imread(str(image_path))
        if image is None:
            QMessageBox.critical(self, "Error", f"Failed to load image: {image_path}")
            return

        self.canvas.set_image(image)
        self.load_labels()
        self.update_info()
        self.canvas.display_image()

    def load_labels(self) -> None:
        self.boxes = []
        image_path = self.image_files[self.current_index]
        label_path = self.labels_dir / f"{image_path.stem}.txt"

        if label_path.exists():
            image = self.canvas.original_image
            h, w = image.shape[:2]
            with open(label_path, "r") as f:
                for line in f:
                    if line.strip():
                        box = BoundingBox.from_yolo(line, w, h)
                        self.boxes.append(box)

    def save_labels(self) -> None:
        image_path = self.image_files[self.current_index]
        label_path = self.labels_dir / f"{image_path.stem}.txt"

        image = self.canvas.original_image
        h, w = image.shape[:2]

        with open(label_path, "w") as f:
            f.writelines(box.to_yolo(w, h) + "\n" for box in self.boxes)

        print(f"Saved labels: {label_path}")

    def add_box(self, box: BoundingBox) -> None:
        self.boxes.append(box)
        self.update_info()

    def delete_last_box(self) -> None:
        if self.boxes:
            self.boxes.pop()
            self.update_info()
            self.canvas.display_image()

    def remove_box_at(self, pos: tuple[int, int]) -> None:
        """Remove the first box (in draw order) containing pos. Used by Ctrl+Click."""
        for box in self.boxes:
            if box.contains_point(pos[0], pos[1]):
                self.boxes.remove(box)
                self.update_info()
                self.canvas.display_image()
                return

    def prev_image(self) -> None:
        self.save_labels()
        self.load_image(self.current_index - 1)

    def next_image(self) -> None:
        self.save_labels()
        self._advance(self.current_index + 1)

    def accept_and_next(self) -> None:
        self.save_labels()
        self._advance(self.current_index + 1)

    def _advance(self, next_index: int) -> None:
        """Move forward to next_index. Auto-closes when past the last image."""
        if next_index >= len(self.image_files):
            self.close()  # auto-save happens in closeEvent
            return
        prev = self.current_index
        self.load_image(next_index)
        if next_index > prev:  # genuine forward move
            self._max_verified_index = max(self._max_verified_index, next_index)
            self._maybe_retrain()

    def _maybe_retrain(self) -> None:
        if not (
            self._retrain_every > 0
            and self._retrain_compute_fn is not None
            and self._max_verified_index > 0
            and self._max_verified_index % self._retrain_every == 0
        ):
            return

        n = self._max_verified_index // self._retrain_every
        self.setWindowTitle(
            f"Retraining #{n}… please wait (check console for progress)"
        )
        self.setEnabled(False)

        thread = RetrainThread(self._retrain_compute_fn, self._max_verified_index)
        thread.finished.connect(self._after_retrain)
        self._retrain_thread = thread  # prevent GC
        thread.start()

    def _after_retrain(self, new_model_path: str) -> None:
        """Called on the main thread when the background retrain thread finishes."""
        if self._retrain_post_fn and new_model_path:
            self._retrain_post_fn(new_model_path, self._max_verified_index)

        # Reload current image's labels (may have been updated by re-annotation)
        self.load_labels()
        self.canvas.display_image()
        self.setEnabled(True)
        self.setWindowTitle(f"Annotator - {self.mode.capitalize()} Mode")
        self.update_info()

    def on_class_changed(self, index: int) -> None:
        self.current_class = index

    def abort_session(self) -> None:
        reply = QMessageBox.question(
            self,
            "Abort session?",
            "Abort this session?\n\nAll captures and annotations for this run will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.aborted = True
            self.close()

    def closeEvent(self, event) -> None:
        """Auto-save on normal close; skip save on abort."""
        if not self.aborted:
            self.save_labels()
        event.accept()

    def get_color(self, class_id: int) -> tuple[int, int, int]:
        colors = config.get(
            "gui.colors",
            [
                [255, 0, 0],
                [0, 255, 0],
                [0, 0, 255],
                [255, 255, 0],
                [255, 0, 255],
                [0, 255, 255],
            ],
        )
        return tuple(colors[class_id % len(colors)])


def run_annotator(
    images_dir: str,
    labels_dir: str,
    classes: list[str],
    mode: str = "annotate",
    retrain_every: int = 0,
    retrain_callback=None,
    retrain_compute_fn=None,
    retrain_post_fn=None,
) -> None:
    """
    Run annotation GUI.

    Args:
        retrain_every: In verify mode, trigger retrain after every N forward moves (0 = disabled).
        retrain_compute_fn: fn(verified_count) -> str — runs in background thread, returns new model path.
        retrain_post_fn: fn(model_path, verified_count) — runs on main thread after compute (live viewer, re-annotate).
        retrain_callback: Legacy single-callback form (compute only, no post step).

    Raises:
        AnnotatorAborted: if the user clicks Abort.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = AnnotatorGUI(
        images_dir,
        labels_dir,
        classes,
        mode,
        retrain_every=retrain_every,
        retrain_callback=retrain_callback,
    )
    # Preferred split-callback form
    if retrain_compute_fn is not None:
        window._retrain_compute_fn = retrain_compute_fn
    if retrain_post_fn is not None:
        window._retrain_post_fn = retrain_post_fn

    window.show()
    app.exec()

    if window.aborted:
        raise AnnotatorAborted("User aborted annotation session.")


if __name__ == "__main__":
    sys.exit(
        run_annotator(
            images_dir="data/captures/examples",
            labels_dir="data/captures/examples_labels",
            classes=["enemy", "item"],
            mode="annotate",
        )
    )
