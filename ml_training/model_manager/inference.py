"""YOLO inference and prediction utilities."""

from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from ..config import SUPPORTED_IMAGE_PATTERNS, config


class YOLOInference:
    """YOLO model inference wrapper."""

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float | None = None,
        iou_threshold: float | None = None,
    ):
        """
        Initialize YOLO inference.

        Args:
            model_path: Path to trained model
            confidence_threshold: Minimum confidence for predictions
            iou_threshold: IoU threshold for NMS
        """
        self.model_path = model_path
        self.model = YOLO(model_path)

        self.confidence_threshold = confidence_threshold or config.get(
            "inference.confidence_threshold", 0.25
        )
        self.iou_threshold = iou_threshold or config.get(
            "inference.iou_threshold", 0.45
        )

    def predict_single(
        self, image_path: str, conf: float | None = None, iou: float | None = None
    ) -> list[dict]:
        """
        Predict on single image.

        Args:
            image_path: Path to image
            conf: Confidence threshold
            iou: IoU threshold

        Returns:
            List of detection dictionaries
        """
        conf = conf or self.confidence_threshold
        iou = iou or self.iou_threshold

        # Run inference
        results = self.model(image_path, conf=conf, iou=iou)[0]

        # Parse results
        detections = []
        for box in results.boxes:
            detection = {
                "class_id": int(box.cls),
                "class_name": results.names[int(box.cls)],
                "confidence": float(box.conf),
                "bbox": box.xywh[0].tolist(),  # [x_center, y_center, width, height]
                "bbox_xyxy": box.xyxy[0].tolist(),  # [x1, y1, x2, y2]
            }
            detections.append(detection)

        return detections

    def predict_batch(
        self,
        image_paths: list[str],
        conf: float | None = None,
        iou: float | None = None,
    ) -> dict[str, list[dict]]:
        """
        Predict on multiple images.

        Args:
            image_paths: List of image paths
            conf: Confidence threshold
            iou: IoU threshold

        Returns:
            Dictionary mapping image paths to detections
        """
        conf = conf or self.confidence_threshold
        iou = iou or self.iou_threshold

        results_dict = {}

        for image_path in image_paths:
            detections = self.predict_single(image_path, conf=conf, iou=iou)
            results_dict[image_path] = detections

        return results_dict

    def save_predictions_yolo_format(
        self, image_path: str, output_label_path: str, conf: float | None = None
    ) -> int:
        """
        Save predictions in YOLO label format.

        Args:
            image_path: Path to image
            output_label_path: Path to save label file
            conf: Confidence threshold

        Returns:
            Number of detections saved
        """
        # Get image dimensions
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Failed to read image: {image_path}")

        img_height, img_width = img.shape[:2]

        # Get predictions
        detections = self.predict_single(image_path, conf=conf)

        # Write YOLO format labels
        output_label_path = Path(output_label_path)
        output_label_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_label_path, "w") as f:
            for det in detections:
                class_id = det["class_id"]
                x_center, y_center, width, height = det["bbox"]

                # Normalize coordinates
                x_center_norm = x_center / img_width
                y_center_norm = y_center / img_height
                width_norm = width / img_width
                height_norm = height / img_height

                f.write(
                    f"{class_id} {x_center_norm:.6f} {y_center_norm:.6f} {width_norm:.6f} {height_norm:.6f}\n"
                )

        return len(detections)

    def batch_predict_and_save(
        self, images_dir: str, output_labels_dir: str, conf: float | None = None
    ) -> int:
        """
        Predict on all images in directory and save labels.

        Args:
            images_dir: Directory containing images
            output_labels_dir: Directory to save labels
            conf: Confidence threshold

        Returns:
            Total number of detections across all images
        """
        images_dir = Path(images_dir)
        output_labels_dir = Path(output_labels_dir)
        output_labels_dir.mkdir(parents=True, exist_ok=True)

        # Get all images
        image_files = []
        for ext in SUPPORTED_IMAGE_PATTERNS:
            image_files.extend(list(images_dir.glob(ext)))

        total_detections = 0

        for image_path in image_files:
            label_path = output_labels_dir / f"{image_path.stem}.txt"
            count = self.save_predictions_yolo_format(
                str(image_path), str(label_path), conf=conf
            )
            total_detections += count
            print(f"Processed {image_path.name}: {count} detections")

        print(f"\nTotal: {len(image_files)} images, {total_detections} detections")
        return total_detections

    def find_low_confidence_predictions(
        self, images_dir: str, low_conf_threshold: float | None = None
    ) -> list[tuple[str, list[dict]]]:
        """
        Find images with low confidence predictions for manual review.

        Args:
            images_dir: Directory containing images
            low_conf_threshold: Threshold for low confidence

        Returns:
            List of (image_path, low_conf_detections) tuples
        """
        low_conf_threshold = low_conf_threshold or config.get(
            "inference.low_confidence_threshold", 0.5
        )

        images_dir = Path(images_dir)

        # Get all images
        image_files = []
        for ext in SUPPORTED_IMAGE_PATTERNS:
            image_files.extend(list(images_dir.glob(ext)))

        low_conf_images = []

        for image_path in image_files:
            detections = self.predict_single(str(image_path))

            # Filter low confidence detections
            low_conf_dets = [
                d for d in detections if d["confidence"] < low_conf_threshold
            ]

            if low_conf_dets:
                low_conf_images.append((str(image_path), low_conf_dets))

        return low_conf_images

    def visualize_predictions(
        self,
        image_path: str,
        output_path: str | None = None,
        conf: float | None = None,
    ) -> np.ndarray:
        """
        Visualize predictions with bounding boxes.

        Args:
            image_path: Path to image
            output_path: Path to save visualization (None to not save)
            conf: Confidence threshold

        Returns:
            Annotated image
        """
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Failed to read image: {image_path}")

        # Get predictions
        detections = self.predict_single(image_path, conf=conf)

        # Draw bounding boxes
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox_xyxy"]]
            class_name = det["class_name"]
            confidence = det["confidence"]

            # Draw box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw label
            label = f"{class_name}: {confidence:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(
                img,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                (0, 255, 0),
                -1,
            )
            cv2.putText(
                img, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1
            )

        # Save if output path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), img)

        return img


def predict_on_images(
    model_path: str, images_dir: str, output_labels_dir: str, conf: float = 0.25
) -> int:
    """
    Convenience function to predict on images and save labels.

    Args:
        model_path: Path to model
        images_dir: Directory containing images
        output_labels_dir: Directory to save labels
        conf: Confidence threshold

    Returns:
        Total detections
    """
    inference = YOLOInference(model_path)
    return inference.batch_predict_and_save(images_dir, output_labels_dir, conf=conf)
