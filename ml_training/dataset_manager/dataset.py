"""Dataset management for YOLO format datasets."""

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


_IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp'}


def _find_split_dirs(source: Path, data_config: dict, split_name: str):
    """
    Locate the images and labels directories for one split of a YOLO dataset.

    Tries three strategies in order:
    1. Parse the data.yaml 'train'/'val' entry (handles both relative and old
       absolute paths that may point to a different machine).
    2. Old-style layout: source/train/images  → source/train/labels
    3. New-style layout: source/images/train  → source/labels/train

    Returns (images_dir, labels_dir) as Paths, or (None, None) if not found.
    """
    yaml_entry = data_config.get(split_name, '')
    if yaml_entry:
        # Resolve against the 'path' field if present, otherwise relative to source
        base = data_config.get('path', '')
        candidate: Path
        if base:
            candidate = (Path(base) / yaml_entry).resolve()
        else:
            p = Path(yaml_entry)
            candidate = p if p.is_absolute() else (source / yaml_entry).resolve()

        if candidate.exists():
            # Derive labels dir: swap the 'images' component for 'labels'
            parts = list(candidate.parts)
            for i, part in enumerate(parts):
                if part == 'images':
                    parts[i] = 'labels'
                    break
            return candidate, Path(*parts)

    # Old layout: split/images  +  split/labels
    old_img = source / split_name / "images"
    if old_img.exists():
        return old_img, source / split_name / "labels"

    # New layout: images/split  +  labels/split
    new_img = source / "images" / split_name
    if new_img.exists():
        return new_img, source / "labels" / split_name

    return None, None

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
        self.base_path = Path(base_path or config.get('dataset.base_path', 'data/datasets'))
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
    base_path = Path(base_path or config.get('dataset.base_path', 'data/datasets'))
    metadata_file = base_path / name / "metadata.json"
    
    if not metadata_file.exists():
        raise ValueError(f"Dataset not found: {name}")
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    return YOLODataset(name, metadata['classes'], base_path)


def import_existing_dataset(
    source_path: str,
    name: str,
    base_path: Optional[str] = None
) -> YOLODataset:
    """
    Import an existing YOLO-format dataset into the ml_training pipeline.

    Handles datasets with train/val/test splits and both dict and list
    formats for class names in data.yaml.

    Args:
        source_path: Path to existing dataset (containing data.yaml)
        name: Name for the imported dataset
        base_path: Base path for ml_training datasets

    Returns:
        YOLODataset instance
    """
    source = Path(source_path)
    data_yaml_path = source / "data.yaml"

    if not data_yaml_path.exists():
        raise ValueError(f"No data.yaml found in {source_path}")

    # Parse data.yaml
    with open(data_yaml_path, 'r') as f:
        data_config = yaml.safe_load(f)

    # Handle both dict and list formats for names
    names = data_config.get('names', [])
    if isinstance(names, dict):
        # {0: "Character", 1: "Slimy", ...} -> ["Character", "Slimy", ...]
        classes = [names[k] for k in sorted(names.keys())]
    else:
        classes = list(names)

    if not classes:
        raise ValueError(f"No class names found in {data_yaml_path}")

    # Create target dataset
    dataset = YOLODataset(name, classes, base_path)
    for d in [dataset.images_train, dataset.images_val,
              dataset.labels_train, dataset.labels_val]:
        d.mkdir(parents=True, exist_ok=True)

    train_count = 0
    val_count = 0

    for split_name, img_dest, lbl_dest in [
        ("train", dataset.images_train, dataset.labels_train),
        ("val",   dataset.images_val,   dataset.labels_val),
        ("test",  dataset.images_val,   dataset.labels_val),   # fold test → val
    ]:
        split_images, split_labels = _find_split_dirs(source, data_config, split_name)
        if split_images is None:
            continue

        for img_file in split_images.iterdir():
            if img_file.suffix.lower() not in _IMG_EXTS:
                continue
            label_file = split_labels / f"{img_file.stem}.txt"
            if label_file.exists():
                shutil.copy(img_file, img_dest / img_file.name)
                shutil.copy(label_file, lbl_dest / label_file.name)
                if split_name == "train":
                    train_count += 1
                else:
                    val_count += 1

    if train_count + val_count == 0:
        raise ValueError(f"No valid image-label pairs found in {source_path}")

    # Generate data.yaml and metadata
    dataset._generate_data_yaml()
    dataset._save_metadata(train_count, val_count)

    print(f"Imported {train_count + val_count} images ({train_count} train, {val_count} val)")
    print(f"Classes: {classes}")
    print(f"Dataset created: {dataset.dataset_path}")

    return dataset


def merge_datasets(
    source_paths: List[str],
    name: str,
    base_path: Optional[str] = None
) -> YOLODataset:
    """
    Merge multiple existing YOLO datasets into one unified dataset.

    Builds a unified class list and remaps class IDs as needed so that
    all datasets share a consistent class mapping.

    Args:
        source_paths: List of paths to existing YOLO datasets
        name: Name for the merged dataset
        base_path: Base path for output dataset

    Returns:
        YOLODataset instance with merged data
    """
    # Build unified class list from all datasets
    unified_classes = []
    dataset_class_maps = []  # Per-dataset: old_id -> new_id

    for src_path in source_paths:
        data_yaml_path = Path(src_path) / "data.yaml"
        if not data_yaml_path.exists():
            raise ValueError(f"No data.yaml found in {src_path}")

        with open(data_yaml_path, 'r') as f:
            data_config = yaml.safe_load(f)

        names = data_config.get('names', [])
        if isinstance(names, dict):
            classes = [names[k] for k in sorted(names.keys())]
        else:
            classes = list(names)

        # Build remap: old class ID -> new class ID in unified list
        remap = {}
        for old_id, cls_name in enumerate(classes):
            if cls_name not in unified_classes:
                unified_classes.append(cls_name)
            remap[old_id] = unified_classes.index(cls_name)

        dataset_class_maps.append(remap)

    print(f"Unified classes: {unified_classes}")

    # Create merged dataset
    dataset = YOLODataset(name, unified_classes, base_path)
    for d in [dataset.images_train, dataset.images_val,
              dataset.labels_train, dataset.labels_val]:
        d.mkdir(parents=True, exist_ok=True)

    train_count = 0
    val_count = 0

    for src_path, remap in zip(source_paths, dataset_class_maps):
        source = Path(src_path)
        needs_remap = any(k != v for k, v in remap.items())
        src_prefix = source.name

        with open(source / "data.yaml") as f:
            src_data_config = yaml.safe_load(f)

        for split_name, img_dest, lbl_dest in [
            ("train", dataset.images_train, dataset.labels_train),
            ("val",   dataset.images_val,   dataset.labels_val),
            ("test",  dataset.images_val,   dataset.labels_val),
        ]:
            split_images, split_labels = _find_split_dirs(source, src_data_config, split_name)
            if split_images is None:
                continue

            for img_file in split_images.iterdir():
                if img_file.suffix.lower() not in _IMG_EXTS:
                    continue
                label_file = split_labels / f"{img_file.stem}.txt"
                if not label_file.exists():
                    continue

                # Prefix with source name to avoid filename collisions across datasets
                dest_img_name = f"{src_prefix}_{img_file.name}"
                dest_lbl_name = f"{src_prefix}_{img_file.stem}.txt"

                shutil.copy(img_file, img_dest / dest_img_name)

                if needs_remap:
                    with open(label_file, 'r') as f:
                        lines = f.readlines()
                    with open(lbl_dest / dest_lbl_name, 'w') as f:
                        for line in lines:
                            parts = line.strip().split()
                            if parts:
                                old_id = int(parts[0])
                                parts[0] = str(remap.get(old_id, old_id))
                                f.write(' '.join(parts) + '\n')
                else:
                    shutil.copy(label_file, lbl_dest / dest_lbl_name)

                if split_name == "train":
                    train_count += 1
                else:
                    val_count += 1

    if train_count + val_count == 0:
        raise ValueError("No valid image-label pairs found in any source dataset")

    dataset._generate_data_yaml()
    dataset._save_metadata(train_count, val_count)

    print(f"Merged {train_count + val_count} images ({train_count} train, {val_count} val)")
    print(f"From {len(source_paths)} source datasets")
    print(f"Dataset created: {dataset.dataset_path}")

    return dataset
