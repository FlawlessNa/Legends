# ML Training & Model Management

Standalone package for training and managing YOLO detection models for the Legends bot.

## Overview

This package provides tools to:
- Capture game screenshots for training data
- Annotate images with bounding boxes
- Train YOLO models with active learning
- Manage model versions and datasets
- Export trained models for use in botting sessions

## Workflow

### Bootstrap New Class Workflow

1. **Initial Bootstrap Phase**
   - Capture ~10 screenshots of new monster type
   - Manually annotate using the annotation GUI
   - Train mini-model on small dataset

2. **Active Learning Phase**
   - Capture ~100 screenshots
   - Run mini-model predictions
   - Review and correct predictions in GUI

3. **Final Training Phase**
   - Re-train model on complete corrected dataset
   - Evaluate performance
   - Export to production if satisfactory

## Project Structure

```
ml_training/
├── dataset_manager/      # Dataset capture and management
├── model_manager/        # Model training and versioning
├── workflows/            # Complete end-to-end workflows
├── gui/                  # Annotation and verification interfaces
├── data/                 # Data storage (gitignored)
│   ├── raw_images/
│   ├── annotations/
│   ├── datasets/
│   └─��� models/
└── config/               # Configuration files
```

## Installation

```bash
pip install -r ml_training/requirements.txt
```

## Quick Start

```python
from ml_training.workflows import BootstrapNewClass

# Create workflow for new monster type
workflow = BootstrapNewClass(class_name="fire_demon")

# Step 1: Capture and annotate initial samples
workflow.capture_initial_samples(count=10)
workflow.annotate_initial_samples()
workflow.train_mini_model()

# Step 2: Active learning phase
workflow.capture_extended_samples(count=100)
workflow.predict_and_verify()

# Step 3: Final training
workflow.train_final_model()
workflow.evaluate()
workflow.export_to_production()
```

## Configuration

Edit `ml_training/config/settings.yaml` to customize:
- Screen capture settings
- Model training parameters
- Dataset paths
- Export locations
