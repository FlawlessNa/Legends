"""ML Training Package for YOLO model development and management."""

__version__ = "0.1.0"

# Import main components for easier access
from .config import config, get_config
from .dataset_manager import (
    ScreenCapture,
    YOLODataset,
    capture_burst,
    create_dataset,
    load_dataset,
)
from .gui import AnnotatorGUI, run_annotator
from .model_manager import (
    ModelRegistry,
    YOLOInference,
    YOLOTrainer,
    get_registry,
    predict_on_images,
    train_mini_model,
    train_model,
)
from .workflows import BootstrapNewClass

__all__ = [
    # Version
    '__version__',
    # Config
    'config',
    'get_config',
    # Dataset Manager
    'ScreenCapture',
    'capture_burst',
    'YOLODataset',
    'create_dataset',
    'load_dataset',
    # Model Manager
    'YOLOTrainer',
    'train_model',
    'train_mini_model',
    'YOLOInference',
    'predict_on_images',
    'ModelRegistry',
    'get_registry',
    # GUI
    'AnnotatorGUI',
    'run_annotator',
    # Workflows
    'BootstrapNewClass',
]