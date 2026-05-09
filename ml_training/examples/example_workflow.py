"""Example usage of the ML Training package."""

from ml_training.config import config
from ml_training.dataset_manager import (
    ScreenCapture,
    YOLODataset,
    capture_burst,
)
from ml_training.gui import run_annotator
from ml_training.model_manager import (
    YOLOInference,
    YOLOTrainer,
    get_registry,
)
from ml_training.workflows import BootstrapNewClass


def example_screen_capture():
    """Example: Screen capture."""
    print("=" * 60)
    print("EXAMPLE: Screen Capture")
    print("=" * 60)

    # Capture burst
    print("\nCapturing burst of 5 screenshots...")
    image_paths = capture_burst(
        count=5,
        output_dir="data/captures/examples",
        prefix="burst",
        countdown=3,
        interval=1.0
    )
    print(f"Saved {len(image_paths)} images")


def example_dataset_creation():
    """Example: Create YOLO dataset."""
    print("=" * 60)
    print("EXAMPLE: Dataset Creation")
    print("=" * 60)

    # Assuming you have images and labels already
    images_dir = "data/captures/examples"
    labels_dir = "data/captures/examples_labels"

    # Create dataset
    dataset = YOLODataset(
        name="example_dataset",
        classes=["enemy", "item", "boss"]
    )

    dataset.create(
        images_dir=images_dir,
        labels_dir=labels_dir,
        train_split=0.8
    )

    # Get statistics
    stats = dataset.get_stats()
    print(f"Dataset stats: {stats}")

    # Get data.yaml path for training
    data_yaml = dataset.get_data_yaml_path()
    print(f"Data YAML: {data_yaml}")


def example_model_training():
    """Example: Train YOLO model."""
    print("=" * 60)
    print("EXAMPLE: Model Training")
    print("=" * 60)

    # Create trainer
    trainer = YOLOTrainer(model_size='n')  # Nano model

    # Train model
    results = trainer.train(
        data_yaml="data/datasets/example_dataset/data.yaml",
        epochs=50,
        batch_size=16,
        name="example_model"
    )

    # Evaluate
    metrics = trainer.evaluate()
    print(f"Metrics: {metrics}")

    # Save model
    model_path = trainer.get_model_path()
    print(f"Model saved: {model_path}")


def example_inference():
    """Example: Run inference."""
    print("=" * 60)
    print("EXAMPLE: Inference")
    print("=" * 60)

    # Load trained model
    inference = YOLOInference(
        model_path="data/models/runs/example_model/weights/best.pt"
    )

    # Predict on single image
    detections = inference.predict_single("path/to/image.jpg")
    print(f"Detections: {detections}")

    # Batch prediction and save labels
    total = inference.batch_predict_and_save(
        images_dir="data/captures/test_images",
        output_labels_dir="data/captures/test_predictions"
    )
    print(f"Processed {total} images")


def example_model_registry():
    """Example: Model registry."""
    print("=" * 60)
    print("EXAMPLE: Model Registry")
    print("=" * 60)

    registry = get_registry()

    # Register a model
    model_id = registry.register_model(
        name="enemy_detector",
        model_path="data/models/runs/example_model/weights/best.pt",
        dataset_name="enemy_dataset_v1",
        metrics={
            'mAP50': 0.85,
            'mAP50-95': 0.72,
            'precision': 0.88,
            'recall': 0.83
        },
        hyperparameters={
            'epochs': 100,
            'batch_size': 16,
            'model_size': 'n'
        },
        notes="Initial enemy detection model"
    )
    print(f"Registered: {model_id}")

    # List all models
    models = registry.list_models()
    print(f"Total models: {len(models)}")

    # Promote to production
    prod_path = registry.promote_to_production(model_id)
    print(f"Production model: {prod_path}")


def example_annotation_gui():
    """Example: Annotation GUI."""
    print("=" * 60)
    print("EXAMPLE: Annotation GUI")
    print("=" * 60)

    # Run annotator in annotate mode
    run_annotator(
        images_dir="data/captures/examples",
        labels_dir="data/captures/examples_labels",
        classes=["enemy", "item", "boss"],
        mode="annotate"
    )


def example_bootstrap_workflow():
    """Example: Complete bootstrap workflow."""
    print("=" * 60)
    print("EXAMPLE: Bootstrap Workflow")
    print("=" * 60)

    # Create workflow for new monster type
    workflow = BootstrapNewClass(class_name="fire_demon")

    # Phase 1: Initial Bootstrap
    print("\n--- Phase 1: Initial Bootstrap ---")
    workflow.capture_initial_samples(count=10)
    workflow.annotate_initial_samples()  # Opens GUI
    workflow.train_mini_model()

    # Phase 2: Active Learning
    print("\n--- Phase 2: Active Learning ---")
    workflow.capture_extended_samples(count=100)
    workflow.predict_and_verify()  # Opens GUI with predictions

    # Phase 3: Final Training
    print("\n--- Phase 3: Final Training ---")
    workflow.train_final_model()
    workflow.evaluate()
    workflow.export_to_production()

    print("\n" + "=" * 60)
    print("Workflow complete!")
    print("=" * 60)


if __name__ == "__main__":
    print("""
ML Training Package Examples
=============================

Uncomment the example you want to run:

1. Screen Capture
2. Dataset Creation
3. Model Training
4. Inference
5. Model Registry
6. Annotation GUI
7. Bootstrap Workflow (Complete)

Note: Make sure you have the required data in place for each example.
    """)

    # Uncomment to run examples:

    # example_screen_capture()
    # example_dataset_creation()
    # example_model_training()
    # example_inference()
    # example_model_registry()
    # example_annotation_gui()
    # example_bootstrap_workflow()
