"""
Convert flat dataset structure to standard nested structure.

Standard structure:
  dataset/
  ├── images/
  │   ├── train/
  │   ├── val/
  │   └── test/
  ├── labels/
  │   ├── train/
  │   ├── val/
  │   └── test/
  └── data.yaml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def convert_to_nested(dataset_path: str) -> None:
    """Convert flat dataset to nested structure."""
    dataset = Path(dataset_path)
    images_dir = dataset / "images"
    labels_dir = dataset / "labels"

    if not images_dir.exists() or not labels_dir.exists():
        print(f"✗ {dataset.name}: Missing images/ or labels/ directory")
        return

    # Check if already nested (has train/val subdirs)
    has_subdirs = any((images_dir / d).is_dir() for d in ["train", "val", "test"])
    if has_subdirs:
        print(f"✓ {dataset.name}: Already nested structure")
        return

    # Check if flat (has image files at root)
    flat_images = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png"))
    if not flat_images:
        print(f"✗ {dataset.name}: No images found")
        return

    print(
        f"Converting {dataset.name} to nested structure ({len(flat_images)} images)..."
    )

    # Create nested dirs
    train_images = images_dir / "train"
    train_labels = labels_dir / "train"
    train_images.mkdir(parents=True, exist_ok=True)
    train_labels.mkdir(parents=True, exist_ok=True)

    # Move all files to train/
    for img_file in flat_images:
        dest = train_images / img_file.name
        print(f"  Moving image: {img_file.name}")
        img_file.replace(dest)

    flat_labels = list(labels_dir.glob("*.txt"))
    for lbl_file in flat_labels:
        dest = train_labels / lbl_file.name
        print(f"  Moving label: {lbl_file.name}")
        lbl_file.replace(dest)

    print(f"✓ {dataset.name}: Converted successfully")


def main():
    datasets = [
        "data/datasets/GS2MobsAndChar",
        "data/datasets/ChronosAndMp3WithCharacter",
        "data/datasets/Bubbling_final",
        "data/datasets/PacPinky_final",
        "data/datasets/Bubbling_combined",
        "data/datasets/PacPinky_combined",
    ]

    print(
        "Standardizing dataset structure to: images/{train,val,test} + labels/{train,val,test}\n"
    )

    for dataset_path in datasets:
        if Path(dataset_path).exists():
            convert_to_nested(dataset_path)
        else:
            print(f"✗ {Path(dataset_path).name}: Not found")

    print("\n" + "=" * 60)
    print("STANDARDIZATION COMPLETE")
    print("=" * 60)
    print("\nAll datasets now use consistent nested structure:")
    print("  images/{train,val} + labels/{train,val}")


if __name__ == "__main__":
    main()
