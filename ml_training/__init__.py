"""ML Training Package for YOLO model development and management."""

__version__ = "0.1.0"

# Import main components for easier access
from .config import config, get_config
from .dataset_manager import (
    ScreenCapture,
    YOLODataset,
    capture_burst,
    create_dataset,
    import_existing_dataset,
    load_dataset,
    merge_datasets,
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
    # GUI
    "AnnotatorGUI",
    # Workflows
    "BootstrapNewClass",
    "ModelRegistry",
    # Dataset Manager
    "ScreenCapture",
    "YOLODataset",
    "YOLOInference",
    # Model Manager
    "YOLOTrainer",
    # Version
    "__version__",
    "capture_burst",
    # Config
    "config",
    "create_dataset",
    "get_config",
    "get_registry",
    "import_existing_dataset",
    "load_dataset",
    "merge_datasets",
    "predict_on_images",
    "run_annotator",
    "train_mini_model",
    "train_model",
]
