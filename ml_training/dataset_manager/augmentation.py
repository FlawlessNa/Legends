"""Data augmentation utilities for increasing dataset size."""

import random
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..config import config


class DataAugmentation:
    """Data augmentation for YOLO format datasets."""
    
    def __init__(
        self,
        brightness_range: Optional[Tuple[float, float]] = None,
        contrast_range: Optional[Tuple[float, float]] = None,
        noise_std: Optional[float] = None,
        horizontal_flip: bool = True
    ):
        """
        Initialize data augmentation.
        
        Args:
            brightness_range: Brightness adjustment range (min, max)
            contrast_range: Contrast adjustment range (min, max)
            noise_std: Standard deviation for Gaussian noise
            horizontal_flip: Whether to apply horizontal flipping
        """
        self.brightness_range = brightness_range or config.get('augmentation.brightness_range', [0.8, 1.2])
        self.contrast_range = contrast_range or config.get('augmentation.contrast_range', [0.8, 1.2])
        self.noise_std = noise_std or config.get('augmentation.noise_std', 10)
        self.horizontal_flip = horizontal_flip if horizontal_flip is not None else config.get('augmentation.horizontal_flip', True)
    
    def adjust_brightness(self, image: np.ndarray, factor: Optional[float] = None) -> np.ndarray:
        """
        Adjust image brightness.
        
        Args:
            image: Input image
            factor: Brightness factor (uses random if None)
            
        Returns:
            Adjusted image
        """
        if factor is None:
            factor = random.uniform(*self.brightness_range)
        
        # Convert to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        
        # Adjust V channel
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] * factor, 0, 255)
        
        # Convert back to BGR
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    
    def adjust_contrast(self, image: np.ndarray, factor: Optional[float] = None) -> np.ndarray:
        """
        Adjust image contrast.
        
        Args:
            image: Input image
            factor: Contrast factor (uses random if None)
            
        Returns:
            Adjusted image
        """
        if factor is None:
            factor = random.uniform(*self.contrast_range)
        
        # Adjust contrast
        mean = np.mean(image)
        adjusted = (image - mean) * factor + mean
        return np.clip(adjusted, 0, 255).astype(np.uint8)
    
    def add_gaussian_noise(self, image: np.ndarray, std: Optional[float] = None) -> np.ndarray:
        """
        Add Gaussian noise to image.
        
        Args:
            image: Input image
            std: Noise standard deviation (uses config if None)
            
        Returns:
            Noisy image
        """
        if std is None:
            std = self.noise_std
        
        noise = np.random.normal(0, std, image.shape)
        noisy = image.astype(np.float32) + noise
        return np.clip(noisy, 0, 255).astype(np.uint8)
    
    def horizontal_flip_image(self, image: np.ndarray) -> np.ndarray:
        """
        Flip image horizontally.
        
        Args:
            image: Input image
            
        Returns:
            Flipped image
        """
        return cv2.flip(image, 1)
    
    def horizontal_flip_boxes(self, boxes: List[List[float]], img_width: int) -> List[List[float]]:
        """
        Flip bounding boxes horizontally (YOLO format).
        
        Args:
            boxes: List of boxes in YOLO format [class, x_center, y_center, width, height]
            img_width: Image width (not used for normalized coordinates)
            
        Returns:
            Flipped boxes
        """
        flipped_boxes = []
        for box in boxes:
            class_id, x_center, y_center, width, height = box
            # Flip x coordinate (YOLO uses normalized coordinates)
            x_center_flipped = 1.0 - x_center
            flipped_boxes.append([class_id, x_center_flipped, y_center, width, height])
        return flipped_boxes
    
    def augment_image_and_labels(
        self,
        image_path: str,
        label_path: str,
        output_dir: str,
        suffix: str = "_aug"
    ) -> Tuple[str, str]:
        """
        Augment single image and its labels.
        
        Args:
            image_path: Path to image file
            label_path: Path to label file (YOLO format)
            output_dir: Output directory
            suffix: Suffix for augmented files
            
        Returns:
            Tuple of (augmented_image_path, augmented_label_path)
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Failed to read image: {image_path}")
        
        # Read labels
        boxes = []
        label_path = Path(label_path)
        if label_path.exists():
            with open(label_path, 'r') as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split()
                        class_id = int(parts[0])
                        coords = [float(x) for x in parts[1:5]]
                        boxes.append([class_id] + coords)
        
        # Apply augmentations
        aug_image = image.copy()
        aug_boxes = boxes.copy()
        
        # Random brightness
        if random.random() > 0.5:
            aug_image = self.adjust_brightness(aug_image)
        
        # Random contrast
        if random.random() > 0.5:
            aug_image = self.adjust_contrast(aug_image)
        
        # Random noise
        if random.random() > 0.3:
            aug_image = self.add_gaussian_noise(aug_image)
        
        # Horizontal flip
        if self.horizontal_flip and random.random() > 0.5:
            aug_image = self.horizontal_flip_image(aug_image)
            aug_boxes = self.horizontal_flip_boxes(aug_boxes, image.shape[1])
        
        # Save augmented image
        image_name = Path(image_path).stem
        image_ext = Path(image_path).suffix
        aug_image_path = output_dir / f"{image_name}{suffix}{image_ext}"
        cv2.imwrite(str(aug_image_path), aug_image)
        
        # Save augmented labels
        aug_label_path = output_dir / f"{image_name}{suffix}.txt"
        with open(aug_label_path, 'w') as f:
            for box in aug_boxes:
                class_id, x_center, y_center, width, height = box
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
        
        return str(aug_image_path), str(aug_label_path)
    
    def augment_dataset(
        self,
        images_dir: str,
        labels_dir: str,
        output_images_dir: str,
        output_labels_dir: str,
        multiplier: int = 3
    ) -> int:
        """
        Augment entire dataset.
        
        Args:
            images_dir: Directory containing images
            labels_dir: Directory containing labels
            output_images_dir: Output directory for augmented images
            output_labels_dir: Output directory for augmented labels
            multiplier: How many augmented versions per image
            
        Returns:
            Total number of augmented images created
        """
        images_dir = Path(images_dir)
        labels_dir = Path(labels_dir)
        output_images_dir = Path(output_images_dir)
        output_labels_dir = Path(output_labels_dir)
        
        output_images_dir.mkdir(parents=True, exist_ok=True)
        output_labels_dir.mkdir(parents=True, exist_ok=True)
        
        # Get all images
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            image_files.extend(list(images_dir.glob(ext)))
        
        total_augmented = 0
        
        for image_path in image_files:
            label_path = labels_dir / f"{image_path.stem}.txt"
            
            # Create multiple augmented versions
            for i in range(multiplier):
                try:
                    aug_img_path, aug_label_path = self.augment_image_and_labels(
                        str(image_path),
                        str(label_path),
                        str(output_images_dir),
                        suffix=f"_aug{i+1}"
                    )
                    
                    # Move label to correct directory
                    final_label_path = output_labels_dir / Path(aug_label_path).name
                    Path(aug_label_path).rename(final_label_path)
                    
                    total_augmented += 1
                except Exception as e:
                    print(f"Error augmenting {image_path}: {e}")
        
        print(f"Created {total_augmented} augmented images")
        return total_augmented


def augment_dataset(
    images_dir: str,
    labels_dir: str,
    output_images_dir: str,
    output_labels_dir: str,
    multiplier: int = 3
) -> int:
    """
    Convenience function to augment dataset.
    
    Args:
        images_dir: Directory containing images
        labels_dir: Directory containing labels
        output_images_dir: Output directory for images
        output_labels_dir: Output directory for labels
        multiplier: Augmentation multiplier
        
    Returns:
        Number of augmented images created
    """
    augmenter = DataAugmentation()
    return augmenter.augment_dataset(
        images_dir,
        labels_dir,
        output_images_dir,
        output_labels_dir,
        multiplier
    )
