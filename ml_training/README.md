# ML Training & Model Management

Standalone package for training and managing YOLO detection models for the Legends bot.

## Overview

This package provides a complete toolkit for creating, training, and deploying YOLO object detection models using an active learning workflow. It's designed to make it easy to train custom detection models for game objects like enemies, items, and bosses.

### Key Features

- **Screen Capture**: Capture game screenshots for training data
- **Annotation GUI**: PyQt6-based interface for labeling images
- **YOLO Training**: Wrapper around Ultralytics YOLO with optimized settings
- **Active Learning**: Bootstrap workflow to maximize efficiency with limited data
- **Model Registry**: Version control and management for trained models
- **Data Augmentation**: Increase dataset size with automated augmentation

## Installation

```bash
# Install dependencies
pip install -r ml_training/requirements.txt

# The package is ready to use without additional setup
```

## Quick Start

### Bootstrap a New Detection Class

The easiest way to train a new model is using the bootstrap workflow:

```python
from ml_training.workflows import BootstrapNewClass

# Create workflow for new monster type
workflow = BootstrapNewClass(class_name="fire_demon")

# Phase 1: Initial Bootstrap (annotate ~10 images)
workflow.capture_initial_samples(count=10)
workflow.annotate_initial_samples()  # Opens annotation GUI
workflow.train_mini_model()

# Phase 2: Active Learning (model helps annotate ~100 more images)
workflow.capture_extended_samples(count=100)
workflow.predict_and_verify()  # Opens verification GUI

# Phase 3: Final Training
workflow.train_final_model()
workflow.evaluate()
workflow.export_to_production()
```

### Manual Workflow

For more control, you can use individual components:

```python
from ml_training import (
    capture_burst,
    run_annotator,
    create_dataset,
    train_model,
    get_registry,
)

# 1. Capture screenshots
capture_burst(count=50, prefix="enemy", countdown=3)

# 2. Annotate images
run_annotator(
    images_dir="ml_training/data/raw_images",
    labels_dir="ml_training/data/annotations",
    classes=["enemy", "item"],
    mode="annotate"
)

# 3. Create YOLO dataset
dataset = create_dataset(
    name="my_dataset",
    classes=["enemy", "item"],
    images_dir="ml_training/data/raw_images",
    labels_dir="ml_training/data/annotations"
)

# 4. Train model
trainer = train_model(
    data_yaml=dataset.get_data_yaml_path(),
    model_size='n',
    epochs=100
)

# 5. Register in model registry
registry = get_registry()
registry.register_model(
    name="enemy_detector",
    model_path=trainer.get_model_path(),
    dataset_name="my_dataset",
    metrics=trainer.evaluate()
)
```

## Project Structure

```
ml_training/
├── __init__.py                 # Package exports
├── README.md                   # This file
├── requirements.txt            # Dependencies
├── .gitignore                  # Excludes data directories
│
├── config/                     # Configuration
│   ├── __init__.py
│   ├── settings.yaml          # Main configuration file
│   └── config.py              # Config loader
│
├── dataset_manager/            # Dataset tools
│   ├── __init__.py
│   ├── capture.py             # Screen capture utilities
│   ├── dataset.py             # YOLO dataset management
│   └── augmentation.py        # Data augmentation
│
├── model_manager/              # Model training and inference
│   ├── __init__.py
│   ├── trainer.py             # YOLO training wrapper
│   ├── inference.py           # Prediction utilities
│   └── versioning.py          # Model registry
│
├── gui/                        # GUI components
│   ├── __init__.py
│   └── annotator.py           # Annotation/verification GUI
│
├── workflows/                  # End-to-end workflows
│   ├── __init__.py
│   └── bootstrap.py           # Bootstrap new class workflow
│
├── examples/                   # Usage examples
│   └── example_workflow.py    # Comprehensive examples
│
└── data/                       # Data storage (gitignored)
    ├── raw_images/            # Captured screenshots
    ├── annotations/           # Manual annotations
    ├── datasets/              # YOLO format datasets
    └── models/                # Trained models
        └── production/        # Production models
```

## Active Learning Workflow

The bootstrap workflow implements an efficient active learning approach:

### Phase 1: Initial Bootstrap (~10 images)
1. **Capture** a small set of representative images
2. **Annotate** manually using the GUI
3. **Train** a mini-model with aggressive augmentation

### Phase 2: Active Learning (~100 images)
1. **Capture** a larger set of images
2. **Predict** using the mini-model
3. **Verify** predictions in GUI (much faster than annotating from scratch)
4. Model suggestions are often correct, you just need to review/correct

### Phase 3: Final Training
1. **Combine** all annotated data
2. **Train** full model with proper hyperparameters
3. **Evaluate** performance metrics
4. **Export** to production if satisfactory

This approach is **10x faster** than annotating 110 images from scratch!

## Components

### Screen Capture

Capture game screenshots with countdown and burst modes:

```python
from ml_training import ScreenCapture, capture_single, capture_burst

# Single screenshot with countdown
capture_single(prefix="enemy", countdown=3)

# Burst mode - multiple captures with intervals
capture_burst(count=50, interval=0.5, countdown=3)

# Advanced usage
capturer = ScreenCapture(output_dir="my_captures")
capturer.set_region(x=100, y=100, width=800, height=600)
capturer.capture_burst(count=20)
```

### Dataset Management

Create and manage YOLO format datasets:

```python
from ml_training import YOLODataset, create_dataset

# Create dataset
dataset = create_dataset(
    name="my_dataset",
    classes=["enemy", "boss", "item"],
    images_dir="path/to/images",
    labels_dir="path/to/labels",
    train_split=0.8  # 80% train, 20% validation
)

# Get dataset info
stats = dataset.get_stats()
print(f"Train images: {stats['train']['images']}")
print(f"Class counts: {stats['class_counts']}")

# Get data.yaml for training
data_yaml = dataset.get_data_yaml_path()
```

### Data Augmentation

Multiply your dataset with automated augmentation:

```python
from ml_training import augment_dataset

# Create 3x augmented versions
count = augment_dataset(
    images_dir="path/to/images",
    labels_dir="path/to/labels",
    output_images_dir="path/to/augmented/images",
    output_labels_dir="path/to/augmented/labels",
    multiplier=3  # 3 augmented versions per image
)
```

Augmentation includes:
- Brightness/contrast adjustment
- Gaussian noise
- Horizontal flipping (with bbox adjustment)

### Model Training

Train YOLO models with optimized settings:

```python
from ml_training import YOLOTrainer

trainer = YOLOTrainer(model_size='n')  # n, s, m, l, or x

# Mini-model for small datasets (aggressive augmentation)
trainer.train_mini_model(
    data_yaml="path/to/data.yaml",
    epochs=50,
    name="mini_model"
)

# Full training for final model
trainer.train(
    data_yaml="path/to/data.yaml",
    epochs=100,
    batch_size=16,
    name="final_model"
)

# Evaluate
metrics = trainer.evaluate()
print(f"mAP50-95: {metrics['mAP50-95']}")
print(f"Precision: {metrics['precision']}")
print(f"Recall: {metrics['recall']}")
```

### Inference

Run predictions on new images:

```python
from ml_training import YOLOInference

inference = YOLOInference(model_path="path/to/model.pt")

# Predict single image
detections = inference.predict_single("image.jpg")
for det in detections:
    print(f"{det['class_name']}: {det['confidence']:.2f}")

# Batch prediction and save YOLO format labels
inference.batch_predict_and_save(
    images_dir="path/to/images",
    output_labels_dir="path/to/labels"
)

# Find low confidence predictions for review
low_conf = inference.find_low_confidence_predictions(
    images_dir="path/to/images",
    low_conf_threshold=0.5
)

# Visualize predictions
inference.visualize_predictions(
    "image.jpg",
    output_path="annotated.jpg"
)
```

### Model Registry

Track and manage model versions:

```python
from ml_training import get_registry

registry = get_registry()

# Register a trained model
model_id = registry.register_model(
    name="enemy_detector",
    model_path="path/to/model.pt",
    dataset_name="enemy_dataset_v1",
    metrics={'mAP50-95': 0.85, 'precision': 0.90},
    hyperparameters={'epochs': 100, 'batch_size': 16},
    notes="First production model"
)

# List all models
models = registry.list_models()

# Get latest version
latest = registry.get_latest_model("enemy_detector")

# Compare models
comparison = registry.compare_models([
    "enemy_detector_v1",
    "enemy_detector_v2"
])

# Promote to production
prod_path = registry.promote_to_production(model_id)
```

### Annotation GUI

Interactive annotation and verification interface:

```python
from ml_training import run_annotator

# Annotate from scratch
run_annotator(
    images_dir="path/to/images",
    labels_dir="path/to/labels",
    classes=["enemy", "boss", "item"],
    mode="annotate"
)

# Verify predictions (much faster!)
run_annotator(
    images_dir="path/to/images",
    labels_dir="path/to/predictions",
    classes=["enemy", "boss", "item"],
    mode="verify"
)
```

**Keyboard Shortcuts:**
- **A/D**: Previous/Next image
- **Click & Drag**: Draw bounding box
- **Del**: Delete last box
- **Ctrl+S**: Save annotations
- **Enter**: Accept and next (verify mode)

## Configuration

Edit `ml_training/config/settings.yaml` to customize:

```yaml
# Screen capture settings
screen_capture:
  countdown: 3
  burst_interval: 0.5
  output_dir: "ml_training/data/raw_images"

# Model training settings
model:
  base_model: "yolov8n.pt"
  image_size: 640
  
  mini_training:
    epochs: 50
    batch_size: 8
  
  final_training:
    epochs: 100
    batch_size: 16

# Bootstrap workflow settings
bootstrap:
  initial_samples: 10
  extended_samples: 100
```

Access configuration in code:

```python
from ml_training.config import config

countdown = config.get('screen_capture.countdown')
config.set('screen_capture.countdown', 5)
```

## Examples

See `ml_training/examples/example_workflow.py` for comprehensive examples of all features.

## Tips & Best Practices

### Dataset Quality
- **Variety**: Capture images in different lighting, positions, and situations
- **Balance**: Try to have similar numbers of each class
- **Quality > Quantity**: 50 well-annotated images beat 200 rushed ones

### Annotation
- Draw **tight** bounding boxes around objects
- Be **consistent** with what you include/exclude
- Review your annotations - mistakes compound in training

### Training
- Start with **nano (n)** models for quick iteration
- Use **mini-model** training for initial datasets < 30 images
- Monitor metrics - if validation is much worse than training, you might be overfitting

### Active Learning
- The mini-model doesn't need to be perfect
- Even 60% accurate predictions are faster to correct than annotating from scratch
- Review low-confidence predictions first

## Model Export for Botting

After training, export your model to production:

```python
workflow.export_to_production()
# Model saved to: ml_training/data/models/production/<class_name>.pt
```

Then reference it in your botting configuration:

```python
# In your bot config
detection_model = "ml_training/data/models/production/fire_demon.pt"
```

## Troubleshooting

### "No images found"
- Check that images are in supported formats: .jpg, .jpeg, .png, .bmp
- Verify the directory path is correct

### "Failed to read image"
- Image might be corrupted
- Try opening it in an image viewer to verify

### GUI doesn't open
- Ensure PyQt6 is installed: `pip install PyQt6`
- On Linux, you might need: `sudo apt-get install python3-pyqt6`

### Training is slow
- Reduce batch_size if running out of memory
- Use a smaller model size (n instead of s or m)
- Reduce image_size in config (e.g., 416 instead of 640)

### Low accuracy
- Need more diverse training data
- Check annotation quality
- Try training longer (more epochs)
- Consider data augmentation

## Advanced Usage

### Custom Augmentation

```python
from ml_training import DataAugmentation

aug = DataAugmentation(
    brightness_range=[0.7, 1.3],
    contrast_range=[0.7, 1.3],
    noise_std=15,
    horizontal_flip=True
)

aug.augment_image_and_labels(
    image_path="image.jpg",
    label_path="label.txt",
    output_dir="augmented/"
)
```

### Multi-Class Training

```python
workflow = BootstrapNewClass(
    class_name="fire_demon",
    additional_classes=["ice_demon", "wind_demon"]
)
# All three classes will be trained together
```

### Custom Model Sizes

```python
# Available sizes: n (nano), s (small), m (medium), l (large), x (extra large)
trainer = YOLOTrainer(model_size='s')  # Bigger, more accurate, slower
```

## Dependencies

- **ultralytics**: YOLO implementation
- **torch**: PyTorch for deep learning
- **opencv-python**: Image processing
- **PyQt6**: GUI framework
- **PyYAML**: Configuration management
- **Pillow**: Image handling
- **numpy**: Numerical operations

See `requirements.txt` for full list with versions.

## License

Part of the Legends project.
