"""Extract class names from a YOLO model and update data.yaml files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ultralytics import YOLO
import yaml


def extract_classes_from_model(model_path: str) -> dict | None:
    """Load YOLO model and extract class names."""
    try:
        model = YOLO(model_path)
        if hasattr(model, 'names'):
            return model.names
        return None
    except Exception as e:
        print(f"ERROR: Failed to load model: {e}")
        return None


def update_data_yaml(dataset_path: str, class_names: dict) -> None:
    """Update data.yaml with extracted class names."""
    yaml_path = Path(dataset_path) / "data.yaml"

    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    # Update class names
    data['names'] = list(class_names.values())
    data['nc'] = len(class_names)

    with open(yaml_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    print(f"✓ Updated {yaml_path}: {data['names']}")


def main():
    model_path = "data/models/production/global/weights/best.pt"

    print(f"Loading model: {model_path}")
    class_names = extract_classes_from_model(model_path)

    if not class_names:
        print("ERROR: Could not extract class names from model.")
        sys.exit(1)

    print(f"\nExtracted {len(class_names)} classes:")
    for idx, name in class_names.items():
        print(f"  {idx}: {name}")

    # Update consolidated datasets
    datasets = [
        "data/datasets/GS2MobsAndChar",
        "data/datasets/ChronosAndMp3WithCharacter",
    ]

    print("\nUpdating data.yaml files...")
    for dataset in datasets:
        if Path(dataset).exists():
            update_data_yaml(dataset, class_names)
        else:
            print(f"✗ Dataset not found: {dataset}")


if __name__ == "__main__":
    main()
