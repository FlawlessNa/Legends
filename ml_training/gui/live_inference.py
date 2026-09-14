"""Live inference viewer for verifying a trained model before proceeding."""

import sys

import numpy as np
from PyQt6.QtCore import QEventLoop, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from ultralytics import YOLO

try:
    from botting.utilities.screenshots import take_screenshot
except ImportError:
    import numpy as _np
    from PIL import ImageGrab

    def take_screenshot(handle=None):
        return _np.array(ImageGrab.grab())


class LiveInferenceViewer(QMainWindow):
    proceed_signal = pyqtSignal()  # emitted on Proceed or window close
    """
    Continuously captures the game window and runs the mini model on each frame.
    Conf/IOU sliders let you find the right thresholds before proceeding.
    """

    def __init__(
        self,
        model_path: str,
        window_handle: int,
        classes: list[str],
        conf: float = 0.15,
        iou: float = 0.45,
    ):
        super().__init__()
        self.window_handle = window_handle
        self.classes = classes
        self._conf = conf
        self._iou = iou
        self._running = True

        print(f"Loading model: {model_path}")
        self.model = YOLO(model_path)

        self._build_ui()

        # Start update loop — singleShot so inference time doesn't stack
        QTimer.singleShot(100, self._update)

    def _build_ui(self) -> None:
        self.setWindowTitle("Live Inference — adjust thresholds, then click Proceed")
        self.setGeometry(80, 80, 1100, 760)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(6)

        # Frame display
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet("background-color: #111;")
        layout.addWidget(self.canvas, stretch=1)

        # Detection info
        self.info_label = QLabel("Waiting for first frame…")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        # Controls row
        controls = QHBoxLayout()

        # Confidence slider
        controls.addWidget(QLabel("Confidence:"))
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(1, 95)
        self.conf_slider.setValue(int(self._conf * 100))
        self.conf_slider.setFixedWidth(220)
        self.conf_slider.valueChanged.connect(self._on_conf_changed)
        controls.addWidget(self.conf_slider)
        self.conf_val_label = QLabel(f"{self._conf:.2f}")
        self.conf_val_label.setFixedWidth(36)
        controls.addWidget(self.conf_val_label)

        controls.addSpacing(24)

        # IOU slider
        controls.addWidget(QLabel("IOU (NMS):"))
        self.iou_slider = QSlider(Qt.Orientation.Horizontal)
        self.iou_slider.setRange(1, 95)
        self.iou_slider.setValue(int(self._iou * 100))
        self.iou_slider.setFixedWidth(220)
        self.iou_slider.valueChanged.connect(self._on_iou_changed)
        controls.addWidget(self.iou_slider)
        self.iou_val_label = QLabel(f"{self._iou:.2f}")
        self.iou_val_label.setFixedWidth(36)
        controls.addWidget(self.iou_val_label)

        controls.addStretch()

        # Proceed button
        self.proceed_btn = QPushButton("Proceed →")
        self.proceed_btn.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold;"
            " padding: 6px 24px; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self.proceed_btn.clicked.connect(self._on_proceed)
        controls.addWidget(self.proceed_btn)

        layout.addLayout(controls)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_conf_changed(self, value: int) -> None:
        self._conf = value / 100.0
        self.conf_val_label.setText(f"{self._conf:.2f}")

    def _on_iou_changed(self, value: int) -> None:
        self._iou = value / 100.0
        self.iou_val_label.setText(f"{self._iou:.2f}")

    def _on_proceed(self) -> None:
        self._running = False
        self.proceed_signal.emit()
        self.close()

    # ── capture + inference loop ───────────────────────────────────────────────

    def _update(self) -> None:
        if not self._running:
            return

        try:
            frame = take_screenshot(self.window_handle)
        except Exception as e:
            self.info_label.setText(f"Capture error: {e}")
            QTimer.singleShot(500, self._update)
            return

        results = self.model(frame, conf=self._conf, iou=self._iou, verbose=False)
        n_det = len(results[0].boxes)

        # results[0].plot() returns a BGR numpy array with boxes drawn
        annotated: np.ndarray = results[0].plot()

        h, w, _ = annotated.shape
        q_img = QImage(annotated.data, w, h, 3 * w, QImage.Format.Format_BGR888)
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.canvas.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.canvas.setPixmap(pixmap)

        self.info_label.setText(
            f"Detections: {n_det}   |   conf={self._conf:.2f}   iou={self._iou:.2f}"
            f"   |   classes: {', '.join(self.classes)}"
        )

        QTimer.singleShot(350, self._update)

    def closeEvent(self, event) -> None:
        self._running = False
        self.proceed_signal.emit()  # unblock any nested event loop waiting on this
        event.accept()

    # ── result accessors ──────────────────────────────────────────────────────

    @property
    def chosen_conf(self) -> float:
        return self._conf

    @property
    def chosen_iou(self) -> float:
        return self._iou


def run_live_inference(
    model_path: str,
    window_handle: int,
    classes: list[str],
    conf: float = 0.15,
    iou: float = 0.45,
) -> tuple[float, float]:
    """
    Open live inference viewer as the top-level window (uses app.exec).
    Returns (conf, iou) chosen by the user.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    viewer = LiveInferenceViewer(model_path, window_handle, classes, conf, iou)
    viewer.show()
    app.exec()

    return viewer.chosen_conf, viewer.chosen_iou


def run_live_inference_nested(
    model_path: str,
    window_handle: int,
    classes: list[str],
    conf: float = 0.15,
    iou: float = 0.45,
) -> tuple[float, float]:
    """
    Open live inference viewer inside an already-running event loop (e.g. from
    within a Qt callback).  Uses a nested QEventLoop so the caller blocks until
    the user clicks Proceed, without freezing other windows.
    Returns (conf, iou) chosen by the user.
    """
    viewer = LiveInferenceViewer(model_path, window_handle, classes, conf, iou)
    viewer.show()

    loop = QEventLoop()
    viewer.proceed_signal.connect(loop.quit)
    loop.exec()

    return viewer.chosen_conf, viewer.chosen_iou
