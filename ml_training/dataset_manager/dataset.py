"""Dataset management for YOLO format datasets."""

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from ..config import config, SUPPORTED_IMAGE_PATTERNS


class YOLODataset:
    """YOLO format dataset manager."""
    
    def __init__(
        self,
        name: str,
        classes: List[str],
        base_path: Optional[str] = None
    ):
        """
        Initialize YOLO dataset.
        
        Args:
            name: Dataset name
            classes: List of class names
            base_path: Base directory for datasets
        """
        self.name = name
        self.classes = classes
        self.base_path = Path(base_path or config.get('dataset.base_path', 'ml_training/data/datasets'))
        self.dataset_path = self.base_path / name
        
        # Create directory structure
        self.images_train = self.dataset_path / "images" / "train"
        self.images_val = self.dataset_path / "images" / "val"
        self.labels_train = self.dataset_path / "labels" / "train"
        self.labels_val = self.dataset_path / "labels" / "val"
        
        self.metadata_file = self.dataset_path / "metadata.json"
        self.data_yaml_file = self.dataset_path / "data.yaml"
    
    def create(
        self,
        images_dir: str,
        labels_dir: str,
        train_split: Optional[float] = None
    ) -> None:
        """
        Create YOLO dataset from images and labels.
        
        Args:
            images_dir: Directory containing images
            labels_dir: Directory containing YOLO format labels
            train_split: Train/val split ratio (e.g., 0.8 for 80/20 split)
        """
        train_split = train_split if train_split is not None else config.get('dataset.train_val_split', 0.8)
        
        # Create directory structure
        for directory in [self.images_train, self.images_val, self.labels_train, self.labels_val]:
            directory.mkdir(parents=True, exist_ok=True)
        
        images_dir = Path(images_dir)
        labels_dir = Path(labels_dir)
        
        # Get all image files
        image_files = []
        for ext in SUPPORTED_IMAGE_PATTERNS:
            image_files.extend(list(images_dir.glob(ext)))
        
        if not image_files:
            raise ValueError(f"No images found in {images_dir}")
        
        # Filter images that have corresponding labels
        valid_pairs = []
        for img_path in image_files:
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                valid_pairs.append((img_path, label_path))
        
        if not valid_pairs:
            raise ValueError(f"No valid image-label pairs found")
        
        print(f"Found {len(valid_pairs)} valid image-label pairs")
        
        # Shuffle and split
        random.shuffle(valid_pairs)
        split_idx = int(len(valid_pairs) * train_split)
        train_pairs = valid_pairs[:split_idx]
        val_pairs = valid_pairs[split_idx:]
        
        print(f"Split: {len(train_pairs)} train, {len(val_pairs)} val")
        
        # Copy files
        for img_path, label_path in train_pairs:
            shutil.copy(img_path, self.images_train / img_path.name)
            shutil.copy(label_path, self.labels_train / label_path.name)
        
        for img_path, label_path in val_pairs:
            shutil.copy(img_path, self.images_val / img_path.name)
            shutil.copy(label_path, self.labels_val / label_path.name)
        
        # Generate data.yaml
        self._generate_data_yaml()
        
        # Save metadata
        self._save_metadata(len(train_pairs), len(val_pairs))
        
        print(f"Dataset created: {self.dataset_path}")
    
    def _generate_data_yaml(self) -> None:
        """Generate data.yaml file for YOLO training."""
        data = {
            'path': str(self.dataset_path.absolute()),
            'train': 'images/train',
            'val': 'images/val',
            'nc': len(self.classes),
            'names': self.classes
        }
        
        with open(self.data_yaml_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def _save_metadata(self, train_count: int, val_count: int) -> None:
        """
        Save dataset metadata.
        
        Args:
            train_count: Number of training images
            val_count: Number of validation images
        """
        metadata = {
            'name': self.name,
            'classes': self.classes,
            'num_classes': len(self.classes),
            'train_count': train_count,
            'val_count': val_count,
            'total_count': train_count + val_count,
            'created_at': datetime.now().isoformat(),
            'data_yaml': str(self.data_yaml_file)
        }
        
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def get_metadata(self) -> Dict:
        """
        Get dataset metadata.
        
        Returns:
            Metadata dictionary
        """
        if not self.metadata_file.exists():
            return {}
        
        with open(self.metadata_file, 'r') as f:
            return json.load(f)
    
    def get_data_yaml_path(self) -> str:
        """
        Get path to data.yaml file.
        
        Returns:
            Path to data.yaml
        """
        return str(self.data_yaml_file)
    
    def get_stats(self) -> Dict:
        """
        Get dataset statistics.
        
        Returns:
            Statistics dictionary
        """
        stats = {
            'train': {
                'images': len(list(self.images_train.glob('*'))),
                'labels': len(list(self.labels_train.glob('*.txt')))
            },
            'val': {
                'images': len(list(self.images_val.glob('*'))),
                'labels': len(list(self.labels_val.glob('*.txt')))
            }
        }
        
        # Count instances per class
        class_counts = {cls: 0 for cls in self.classes}
        
        for label_file in list(self.labels_train.glob('*.txt')) + list(self.labels_val.glob('*.txt')):
            with open(label_file, 'r') as f:
                for line in f:
                    if line.strip():
                        class_id = int(line.split()[0])
                        if 0 <= class_id < len(self.classes):
                            class_counts[self.classes[class_id]] += 1
        
        stats['class_counts'] = class_counts
        stats['total_instances'] = sum(class_counts.values())
        
        return stats
    
    def exists(self) -> bool:
        """
        Check if dataset exists.
        
        Returns:
            True if dataset exists
        """
        return self.dataset_path.exists() and self.data_yaml_file.exists()


def create_dataset(
    name: str,
    classes: List[str],
    images_dir: str,
    labels_dir: str,
    train_split: float = 0.8
) -> YOLODataset:
    """
    Convenience function to create a YOLO dataset.
    
    Args:
        name: Dataset name
        classes: List of class names
        images_dir: Directory containing images
        labels_dir: Directory containing labels
        train_split: Train/val split ratio
        
    Returns:
        YOLODataset instance
    """
    dataset = YOLODataset(name, classes)
    dataset.create(images_dir, labels_dir, train_split)
    return dataset


def load_dataset(name: str, base_path: Optional[str] = None) -> YOLODataset:
    """
    Load existing YOLO dataset.
    
    Args:
        name: Dataset name
        base_path: Base directory for datasets
        
    Returns:
        YOLODataset instance
    """
    base_path = Path(base_path or config.get('dataset.base_path', 'ml_training/data/datasets'))
    metadata_file = base_path / name / "metadata.json"
    
    if not metadata_file.exists():
        raise ValueError(f"Dataset not found: {name}")
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    return YOLODataset(name, metadata['classes'], base_path)
