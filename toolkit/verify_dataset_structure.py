"""Verify all datasets have consistent structure."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def verify_dataset(dataset_path: Path) -> tuple[bool, str]:
    """
    Verify a dataset has proper structure:
    - dataset/images/{train,val,...}/
    - dataset/labels/{train,val,...}/
    - dataset/data.yaml

    Returns (is_valid, message)
    """
    if not dataset_path.exists():
        return False, "Path does not exist"

    issues = []

    # Check images dir
    images_dir = dataset_path / "images"
    if not images_dir.exists():
        return False, "Missing images/ directory"

    # Check labels dir
    labels_dir = dataset_path / "labels"
    if not labels_dir.exists():
        return False, "Missing labels/ directory"

    # Check for split subdirs (train, val, test)
    split_dirs = {"train", "val", "test"}
    has_split_dirs = any((images_dir / s).is_dir() for s in split_dirs)

    if not has_split_dirs:
        issues.append("No train/val/test subdirs in images/")

    # Count files
    image_files = list(images_dir.glob("*/*.jpg")) + list(images_dir.glob("*/*.png"))
    flat_images = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png"))

    if not image_files and not flat_images:
        return False, "No images found"

    label_files = list(labels_dir.glob("*/*.txt"))
    flat_labels = list(labels_dir.glob("*.txt"))

    if not label_files and not flat_labels:
        issues.append("No labels found")

    # Check data.yaml, and that every label class ID is declared in it
    yaml_path = dataset_path / "data.yaml"
    if not yaml_path.exists():
        issues.append("Missing data.yaml")
    else:
        import yaml
        with open(yaml_path) as f:
            names = yaml.safe_load(f).get("names", [])
        n_classes = len(names)
        bad_ids = set()
        for lbl in list(labels_dir.glob("*/*.txt")) + list(labels_dir.glob("*.txt")):
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts and int(parts[0]) >= n_classes:
                    bad_ids.add(int(parts[0]))
        if bad_ids:
            issues.append(
                f"labels use class ids {sorted(bad_ids)} but data.yaml only declares {n_classes} classes"
            )

    # Check for train/val leakage (same filename in both splits)
    train_names = {p.name for p in (images_dir / "train").glob("*") if p.is_file()}
    val_names = {p.name for p in (images_dir / "val").glob("*") if p.is_file()}
    overlap = train_names & val_names
    if overlap:
        issues.append(f"{len(overlap)} images in BOTH train and val (leakage!)")

    # Check every image has a label and vice versa
    for split in ("train", "val"):
        img_stems = {p.stem for p in (images_dir / split).glob("*") if p.is_file()}
        lbl_stems = {p.stem for p in (labels_dir / split).glob("*.txt")}
        missing_labels = img_stems - lbl_stems
        orphan_labels = lbl_stems - img_stems
        if missing_labels:
            issues.append(f"{len(missing_labels)} {split} images without labels")
        if orphan_labels:
            issues.append(f"{len(orphan_labels)} {split} labels without images")

    status = "✓" if not issues else "⚠"
    msg = f"{status} {len(image_files or flat_images)} images, {len(label_files or flat_labels)} labels"
    if issues:
        msg += f" — {'; '.join(issues)}"

    return len(issues) == 0, msg


def main():
    datasets_dir = Path("data/datasets")

    if not datasets_dir.exists():
        print("ERROR: data/datasets/ not found")
        sys.exit(1)

    print("DATASET STRUCTURE VERIFICATION")
    print("="*60)

    datasets = sorted([d for d in datasets_dir.iterdir() if d.is_dir()])
    valid_count = 0

    for dataset_path in datasets:
        is_valid, msg = verify_dataset(dataset_path)
        print(f"{dataset_path.name:30} {msg}")
        if is_valid:
            valid_count += 1

    print("="*60)
    print(f"Valid: {valid_count}/{len(datasets)}")

    if valid_count < len(datasets):
        print("\nWARNING: Some datasets have issues. Review above.")
        return 1
    else:
        print("\n✓ All datasets have consistent structure!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
