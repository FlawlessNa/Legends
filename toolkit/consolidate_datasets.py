"""
Consolidate legacy dataset structure into new structure.

Legacy: data/character_detection_images/{name}/{split}/images|labels/
New:    data/datasets/{name}/images|labels/ (flat, no splits)

This script:
1. Copies images and labels from legacy {train,val,test} into new flat structure
2. Updates ml_training/run.py to point to new paths
3. Removes empty legacy folder
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def consolidate_dataset(legacy_path: Path, new_name: str) -> None:
    """Move a legacy dataset to new structure, flattening splits."""
    new_path = Path("data/datasets") / new_name

    # Create new structure if doesn't exist
    new_images_dir = new_path / "images"
    new_labels_dir = new_path / "labels"
    new_images_dir.mkdir(parents=True, exist_ok=True)
    new_labels_dir.mkdir(parents=True, exist_ok=True)

    # Merge all splits (train/val/test)
    for split in ["train", "val", "test"]:
        old_images = legacy_path / split / "images"
        old_labels = legacy_path / split / "labels"

        if old_images.exists():
            for img_file in old_images.glob("*"):
                dest = new_images_dir / img_file.name
                if not dest.exists():
                    print(f"  Copying image: {img_file.name}")
                    shutil.copy2(img_file, dest)
                else:
                    print(f"  Skipping (exists): {img_file.name}")

        if old_labels.exists():
            for lbl_file in old_labels.glob("*"):
                dest = new_labels_dir / lbl_file.name
                if not dest.exists():
                    print(f"  Copying label: {lbl_file.name}")
                    shutil.copy2(lbl_file, dest)
                else:
                    print(f"  Skipping (exists): {lbl_file.name}")

    print(f"✓ {new_name}: {new_images_dir.glob('*').__sizeof__()} files")


def update_run_py() -> None:
    """Update GLOBAL_DATASET_PATHS in ml_training/run.py."""
    run_py = Path("ml_training/run.py")
    content = run_py.read_text()

    # Replace old paths with new ones
    old_paths = [
        '"data/character_detection_images/GS2MobsAndChar"',
        '"data/character_detection_images/ChronosAndMp3WithCharacter"',
    ]
    new_paths = [
        '"data/datasets/GS2MobsAndChar"',
        '"data/datasets/ChronosAndMp3WithCharacter"',
    ]

    for old, new in zip(old_paths, new_paths):
        if old in content:
            content = content.replace(old, new)
            print(f"  Updated: {old} → {new}")

    run_py.write_text(content)
    print("✓ Updated ml_training/run.py")


def main():
    legacy_root = Path("data/character_detection_images")

    if not legacy_root.exists():
        print("ERROR: Legacy dataset folder not found.")
        sys.exit(1)

    # Check what to migrate
    legacy_datasets = ["GS2MobsAndChar", "ChronosAndMp3WithCharacter"]
    datasets_to_migrate = [d for d in legacy_datasets if (legacy_root / d).exists()]

    if not datasets_to_migrate:
        print("ERROR: No legacy datasets found to migrate.")
        sys.exit(1)

    print(f"Consolidating {len(datasets_to_migrate)} dataset(s)...")
    for dataset_name in datasets_to_migrate:
        print(f"\n{dataset_name}:")
        consolidate_dataset(legacy_root / dataset_name, dataset_name)

    print("\nUpdating ml_training/run.py...")
    update_run_py()

    print("\n" + "=" * 60)
    print("CONSOLIDATION COMPLETE")
    print("=" * 60)
    print("\nNEXT STEPS:")
    print("1. Verify the new datasets in data/datasets/")
    print("2. Review the changes in ml_training/run.py")
    print("3. Test training with: python ml_training/run.py")
    print("4. Once confirmed working, delete legacy folder:")
    print(f"   Remove-Item -Recurse -Force '{legacy_root}'")
    print("\nOr if you want to delete it now:")
    response = input("\nDelete legacy folder now? (y/N): ").strip().lower()
    if response == "y":
        shutil.rmtree(legacy_root)
        print(f"✓ Deleted {legacy_root}")


if __name__ == "__main__":
    main()
