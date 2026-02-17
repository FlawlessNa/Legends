"""Example usage of the ML Training package."""

from ml_training.config import config
from ml_training.dataset_manager import (
    ScreenCapture,
    YOLODataset,
    augment_dataset,
    capture_burst,
    capture_single,
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
    
    # Capture single screenshot
    print("\nCapturing single screenshot...")
    image_path = capture_single(
        output_dir="ml_training/data/examples/captures",
        prefix="example",
        countdown=3
    )
    print(f"Saved: {image_path}")
    
    # Capture burst
    print("\nCapturing burst of 5 screenshots...")
    image_paths = capture_burst(
        count=5,
        output_dir="ml_training/data/examples/captures",
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
    images_dir = "ml_training/data/examples/images"
    labels_dir = "ml_training/data/examples/labels"
    
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


def example_data_augmentation():
    """Example: Data augmentation."""
    print("=" * 60)
    print("EXAMPLE: Data Augmentation")
    print("=" * 60)
    
    # Augment dataset
    count = augment_dataset(
        images_dir="ml_training/data/examples/images",
        labels_dir="ml_training/data/examples/labels",
        output_images_dir="ml_training/data/examples/augmented/images",
        output_labels_dir="ml_training/data/examples/augmented/labels",
        multiplier=3  # Create 3 augmented versions per image
    )
    
    print(f"Created {count} augmented images")


def example_model_training():
    """Example: Train YOLO model."""
    print("=" * 60)
    print("EXAMPLE: Model Training")
    print("=" * 60)
    
    # Create trainer
    trainer = YOLOTrainer(model_size='n')  # Nano model
    
    # Train model
    results = trainer.train(
        data_yaml="ml_training/data/datasets/example_dataset/data.yaml",
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
        model_path="ml_training/data/models/example_model/weights/best.pt"
    )
    
    # Predict on single image
    detections = inference.predict_single("path/to/image.jpg")
    print(f"Detections: {detections}")
    
    # Batch prediction and save labels
    total = inference.batch_predict_and_save(
        images_dir="ml_training/data/test_images",
        output_labels_dir="ml_training/data/predictions"
    )
    print(f"Processed {total} images")
    
    # Find low confidence predictions
    low_conf = inference.find_low_confidence_predictions(
        images_dir="ml_training/data/test_images"
    )
    print(f"Found {len(low_conf)} images with low confidence predictions")


def example_model_registry():
    """Example: Model registry."""
    print("=" * 60)
    print("EXAMPLE: Model Registry")
    print("=" * 60)
    
    registry = get_registry()
    
    # Register a model
    model_id = registry.register_model(
        name="enemy_detector",
        model_path="ml_training/data/models/example_model/weights/best.pt",
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
    
    # Get latest version
    latest = registry.get_latest_model("enemy_detector")
    print(f"Latest version: {latest['version']}")
    
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
        images_dir="ml_training/data/raw_images",
        labels_dir="ml_training/data/annotations",
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


def example_configuration():
    """Example: Working with configuration."""
    print("=" * 60)
    print("EXAMPLE: Configuration")
    print("=" * 60)
    
    # Get configuration values
    screen_capture_config = config.get('screen_capture')
    print(f"Screen capture config: {screen_capture_config}")
    
    # Get specific value with dot notation
    countdown = config.get('screen_capture.countdown', default=3)
    print(f"Countdown: {countdown}")
    
    # Set configuration value
    config.set('screen_capture.countdown', 5)
    print(f"Updated countdown: {config.get('screen_capture.countdown')}")
    
    # Get model training config
    mini_epochs = config.get('model.mini_training.epochs')
    print(f"Mini training epochs: {mini_epochs}")


if __name__ == "__main__":
    print("""
ML Training Package Examples
=============================

Uncomment the example you want to run:
    
1. Screen Capture
2. Dataset Creation
3. Data Augmentation
4. Model Training
5. Inference
6. Model Registry
7. Annotation GUI
8. Bootstrap Workflow (Complete)
9. Configuration

Note: Make sure you have the required data in place for each example.
    """)
    
    # Uncomment to run examples:
    
    # example_screen_capture()
    # example_dataset_creation()
    # example_data_augmentation()
    # example_model_training()
    # example_inference()
    # example_model_registry()
    # example_annotation_gui()
    # example_bootstrap_workflow()
    # example_configuration()
