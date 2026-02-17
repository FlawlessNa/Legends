"""PyQt6-based annotation and verification GUI."""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt
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

from ..config import config


class BoundingBox:
    """Bounding box representation."""
    
    def __init__(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        class_id: int,
        confidence: float = 1.0
    ):
        """
        Initialize bounding box.
        
        Args:
            x1, y1: Top-left corner
            x2, y2: Bottom-right corner
            class_id: Class ID
            confidence: Confidence score (for predictions)
        """
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.class_id = class_id
        self.confidence = confidence
    
    def to_yolo(self, img_width: int, img_height: int) -> str:
        """
        Convert to YOLO format.
        
        Args:
            img_width: Image width
            img_height: Image height
            
        Returns:
            YOLO format string
        """
        x_center = ((self.x1 + self.x2) / 2) / img_width
        y_center = ((self.y1 + self.y2) / 2) / img_height
        width = (self.x2 - self.x1) / img_width
        height = (self.y2 - self.y1) / img_height
        
        return f"{self.class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
    
    @classmethod
    def from_yolo(cls, line: str, img_width: int, img_height: int) -> 'BoundingBox':
        """
        Create from YOLO format line.
        
        Args:
            line: YOLO format line
            img_width: Image width
            img_height: Image height
            
        Returns:
            BoundingBox instance
        """
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
        """Check if point is inside box."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class AnnotationCanvas(QLabel):
    """Canvas for drawing annotations."""
    
    def __init__(self, parent=None):
        """Initialize canvas."""
        super().__init__(parent)
        self.parent_window = parent
        self.setMouseTracking(True)
        
        self.drawing = False
        self.start_point = None
        self.current_point = None
        self.temp_box = None
        
        self.scale_factor = 1.0
    
    def set_image(self, image: np.ndarray) -> None:
        """Set image to display."""
        self.original_image = image.copy()
        self.display_image()
    
    def display_image(self) -> None:
        """Display image with annotations."""
        if not hasattr(self, 'original_image'):
            return
        
        # Draw boxes on image
        display_img = self.original_image.copy()
        
        # Draw existing boxes
        for box in self.parent_window.boxes:
            color = self.parent_window.get_color(box.class_id)
            cv2.rectangle(display_img, (box.x1, box.y1), (box.x2, box.y2), color, 2)
            
            # Draw class label
            label = self.parent_window.classes[box.class_id]
            cv2.putText(
                display_img,
                label,
                (box.x1, box.y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1
            )
        
        # Draw temporary box while drawing
        if self.temp_box:
            color = self.parent_window.get_color(self.parent_window.current_class)
            cv2.rectangle(
                display_img,
                (self.temp_box.x1, self.temp_box.y1),
                (self.temp_box.x2, self.temp_box.y2),
                color,
                2
            )
        
        # Convert to QPixmap
        height, width, channel = display_img.shape
        bytes_per_line = 3 * width
        q_image = QImage(
            display_img.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_BGR888
        )
        
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit window
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.scale_factor = scaled_pixmap.width() / width
        self.setPixmap(scaled_pixmap)
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Convert to image coordinates
            pos = self.get_image_coords(event.pos())
            if pos:
                self.drawing = True
                self.start_point = pos
    
    def mouseMoveEvent(self, event):
        """Handle mouse move."""
        if self.drawing and self.start_point:
            pos = self.get_image_coords(event.pos())
            if pos:
                self.current_point = pos
                self.temp_box = BoundingBox(
                    self.start_point[0],
                    self.start_point[1],
                    pos[0],
                    pos[1],
                    self.parent_window.current_class
                )
                self.display_image()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            pos = self.get_image_coords(event.pos())
            if pos and self.start_point:
                # Create box if it has minimum size
                if abs(pos[0] - self.start_point[0]) > 5 and abs(pos[1] - self.start_point[1]) > 5:
                    box = BoundingBox(
                        self.start_point[0],
                        self.start_point[1],
                        pos[0],
                        pos[1],
                        self.parent_window.current_class
                    )
                    self.parent_window.add_box(box)
                
                self.drawing = False
                self.start_point = None
                self.current_point = None
                self.temp_box = None
                self.display_image()
    
    def get_image_coords(self, pos: QPoint) -> Optional[Tuple[int, int]]:
        """Convert widget coordinates to image coordinates."""
        if not self.pixmap():
            return None
        
        # Account for scaling and centering
        pixmap_rect = self.pixmap().rect()
        widget_rect = self.rect()
        
        x_offset = (widget_rect.width() - pixmap_rect.width()) // 2
        y_offset = (widget_rect.height() - pixmap_rect.height()) // 2
        
        x = int((pos.x() - x_offset) / self.scale_factor)
        y = int((pos.y() - y_offset) / self.scale_factor)
        
        # Clamp to image bounds
        if hasattr(self, 'original_image'):
            h, w = self.original_image.shape[:2]
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            return (x, y)
        
        return None


class AnnotatorGUI(QMainWindow):
    """Annotation and verification GUI."""
    
    def __init__(
        self,
        images_dir: str,
        labels_dir: str,
        classes: List[str],
        mode: str = "annotate"
    ):
        """
        Initialize annotator GUI.
        
        Args:
            images_dir: Directory containing images
            labels_dir: Directory containing/to save labels
            classes: List of class names
            mode: "annotate" (from scratch) or "verify" (review predictions)
        """
        super().__init__()
        
        self.images_dir = Path(images_dir)
        self.labels_dir = Path(labels_dir)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        
        self.classes = classes
        self.mode = mode
        
        # Get image files
        self.image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            self.image_files.extend(list(self.images_dir.glob(ext)))
        self.image_files = sorted(self.image_files)
        
        if not self.image_files:
            QMessageBox.critical(None, "Error", f"No images found in {images_dir}")
            sys.exit(1)
        
        self.current_index = 0
        self.boxes: List[BoundingBox] = []
        self.current_class = 0
        
        # Setup UI
        self.init_ui()
        
        # Load first image
        self.load_image(0)
    
    def init_ui(self) -> None:
        """Initialize UI components."""
        self.setWindowTitle(f"Annotator - {self.mode.capitalize()} Mode")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
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
        
        # Class selector
        controls_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.classes)
        self.class_combo.currentIndexChanged.connect(self.on_class_changed)
        controls_layout.addWidget(self.class_combo)
        
        # Navigation buttons
        self.prev_btn = QPushButton("Previous (A)")
        self.prev_btn.clicked.connect(self.prev_image)
        controls_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next (D)")
        self.next_btn.clicked.connect(self.next_image)
        controls_layout.addWidget(self.next_btn)
        
        # Action buttons
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_labels)
        controls_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("Delete Last Box (Del)")
        self.delete_btn.clicked.connect(self.delete_last_box)
        controls_layout.addWidget(self.delete_btn)
        
        if self.mode == "verify":
            self.accept_btn = QPushButton("Accept (Enter)")
            self.accept_btn.clicked.connect(self.accept_and_next)
            controls_layout.addWidget(self.accept_btn)
        
        main_layout.addLayout(controls_layout)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("A"), self).activated.connect(self.prev_image)
        QShortcut(QKeySequence("D"), self).activated.connect(self.next_image)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_labels)
        QShortcut(QKeySequence("Del"), self).activated.connect(self.delete_last_box)
        if self.mode == "verify":
            QShortcut(QKeySequence("Return"), self).activated.connect(self.accept_and_next)
    
    def update_info(self) -> None:
        """Update info label."""
        info = f"Image {self.current_index + 1}/{len(self.image_files)} | "
        info += f"Boxes: {len(self.boxes)} | "
        info += f"File: {self.image_files[self.current_index].name}"
        self.info_label.setText(info)
    
    def load_image(self, index: int) -> None:
        """Load image at index."""
        if not 0 <= index < len(self.image_files):
            return
        
        self.current_index = index
        image_path = self.image_files[index]
        
        # Load image
        image = cv2.imread(str(image_path))
        if image is None:
            QMessageBox.critical(self, "Error", f"Failed to load image: {image_path}")
            return
        
        self.canvas.set_image(image)
        
        # Load existing labels
        self.load_labels()
        
        self.update_info()
        self.canvas.display_image()
    
    def load_labels(self) -> None:
        """Load labels for current image."""
        self.boxes = []
        
        image_path = self.image_files[self.current_index]
        label_path = self.labels_dir / f"{image_path.stem}.txt"
        
        if label_path.exists():
            image = self.canvas.original_image
            h, w = image.shape[:2]
            
            with open(label_path, 'r') as f:
                for line in f:
                    if line.strip():
                        box = BoundingBox.from_yolo(line, w, h)
                        self.boxes.append(box)
    
    def save_labels(self) -> None:
        """Save labels for current image."""
        image_path = self.image_files[self.current_index]
        label_path = self.labels_dir / f"{image_path.stem}.txt"
        
        image = self.canvas.original_image
        h, w = image.shape[:2]
        
        with open(label_path, 'w') as f:
            for box in self.boxes:
                f.write(box.to_yolo(w, h) + '\n')
        
        print(f"Saved labels: {label_path}")
    
    def add_box(self, box: BoundingBox) -> None:
        """Add bounding box."""
        self.boxes.append(box)
        self.update_info()
    
    def delete_last_box(self) -> None:
        """Delete last bounding box."""
        if self.boxes:
            self.boxes.pop()
            self.update_info()
            self.canvas.display_image()
    
    def prev_image(self) -> None:
        """Go to previous image."""
        self.save_labels()
        self.load_image(self.current_index - 1)
    
    def next_image(self) -> None:
        """Go to next image."""
        self.save_labels()
        self.load_image(self.current_index + 1)
    
    def accept_and_next(self) -> None:
        """Accept current annotations and go to next."""
        self.save_labels()
        self.load_image(self.current_index + 1)
    
    def on_class_changed(self, index: int) -> None:
        """Handle class selection change."""
        self.current_class = index
    
    def get_color(self, class_id: int) -> Tuple[int, int, int]:
        """Get color for class."""
        colors = config.get('gui.colors', [
            [255, 0, 0], [0, 255, 0], [0, 0, 255],
            [255, 255, 0], [255, 0, 255], [0, 255, 255]
        ])
        return tuple(colors[class_id % len(colors)])


def run_annotator(
    images_dir: str,
    labels_dir: str,
    classes: List[str],
    mode: str = "annotate"
) -> None:
    """
    Run annotation GUI.
    
    Args:
        images_dir: Directory containing images
        labels_dir: Directory containing/to save labels
        classes: List of class names
        mode: "annotate" or "verify"
    """
    app = QApplication(sys.argv)
    window = AnnotatorGUI(images_dir, labels_dir, classes, mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # Example usage
    run_annotator(
        images_dir="ml_training/data/raw_images",
        labels_dir="ml_training/data/annotations",
        classes=["enemy", "item"],
        mode="annotate"
    )
