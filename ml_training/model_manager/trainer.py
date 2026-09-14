"""YOLO model training wrapper."""

from pathlib import Path

from ultralytics import YOLO

from ..config import config


class YOLOTrainer:
    """Wrapper around Ultralytics YOLO for training."""

    def __init__(self, model_size: str = "n", base_model: str | None = None):
        """
        Initialize YOLO trainer.

        Args:
            model_size: Model size (n, s, m, l, x)
            base_model: Path to base model or None to use pretrained
        """
        self.model_size = model_size

        if base_model and Path(base_model).exists():
            self.model = YOLO(base_model)
        else:
            # Use pretrained model
            base_model = base_model or config.get(
                "model.base_model", f"yolov8{model_size}.pt"
            )
            self.model = YOLO(base_model)

    def train(
        self,
        data_yaml: str,
        epochs: int | None = None,
        batch_size: int | None = None,
        image_size: int | None = None,
        patience: int | None = None,
        project: str | None = None,
        name: str | None = None,
        **kwargs: object,
    ) -> dict:
        """
        Train YOLO model.

        Args:
            data_yaml: Path to data.yaml file
            epochs: Number of training epochs
            batch_size: Batch size
            image_size: Image size
            patience: Early stopping patience
            project: Project directory
            name: Run name
            **kwargs: Additional training arguments

        Returns:
            Training results dictionary
        """
        # Get defaults from config
        epochs = epochs or config.get("model.final_training.epochs", 100)
        batch_size = batch_size or config.get("model.final_training.batch_size", 16)
        image_size = image_size or config.get("model.image_size", 640)
        patience = patience or config.get("model.final_training.patience", 20)

        if project is None:
            project = config.get("registry.runs_path", "data/models/runs")

        # Train
        results = self.model.train(
            data=data_yaml,
            epochs=epochs,
            batch=batch_size,
            imgsz=image_size,
            patience=patience,
            project=project,
            name=name,
            **kwargs,
        )

        return results

    def train_mini_model(
        self,
        data_yaml: str,
        epochs: int | None = None,
        batch_size: int | None = None,
        project: str | None = None,
        name: str | None = None,
        **kwargs: object,
    ) -> dict:
        """
        Train mini model with aggressive augmentation for small datasets.

        Args:
            data_yaml: Path to data.yaml file
            epochs: Number of epochs (default from config)
            batch_size: Batch size (default from config)
            project: Project directory
            name: Run name
            **kwargs: Additional training arguments

        Returns:
            Training results dictionary
        """
        # Get mini training config
        epochs = epochs or config.get("model.mini_training.epochs", 50)
        batch_size = batch_size or config.get("model.mini_training.batch_size", 8)
        image_size = config.get("model.image_size", 640)
        patience = config.get("model.mini_training.patience", 10)

        if project is None:
            project = config.get("registry.runs_path", "data/models/runs")

        # Aggressive augmentation parameters
        aug_params = {
            "hsv_h": config.get("model.mini_training.hsv_h", 0.02),
            "hsv_s": config.get("model.mini_training.hsv_s", 0.7),
            "hsv_v": config.get("model.mini_training.hsv_v", 0.4),
            "degrees": config.get("model.mini_training.degrees", 10),
            "translate": config.get("model.mini_training.translate", 0.2),
            "scale": config.get("model.mini_training.scale", 0.5),
            "shear": config.get("model.mini_training.shear", 0.0),
            "perspective": config.get("model.mini_training.perspective", 0.0),
            "flipud": config.get("model.mini_training.flipud", 0.0),
            "fliplr": config.get("model.mini_training.fliplr", 0.5),
            "mosaic": config.get("model.mini_training.mosaic", 1.0),
            "mixup": config.get("model.mini_training.mixup", 0.15),
        }

        # Merge with kwargs
        train_params = {**aug_params, **kwargs}

        # Train
        results = self.model.train(
            data=data_yaml,
            epochs=epochs,
            batch=batch_size,
            imgsz=image_size,
            patience=patience,
            project=project,
            name=name,
            **train_params,
        )

        return results

    def evaluate(self, data_yaml: str | None = None, split: str = "val") -> dict:
        """
        Evaluate model on validation set.

        Args:
            data_yaml: Path to data.yaml (not needed if already trained)
            split: Dataset split to evaluate on ('val' or 'test')

        Returns:
            Evaluation metrics dictionary
        """
        if data_yaml:
            results = self.model.val(data=data_yaml, split=split)
        else:
            results = self.model.val(split=split)

        # Extract key metrics
        metrics = {
            "mAP50": results.box.map50,
            "mAP50-95": results.box.map,
            "precision": results.box.mp,
            "recall": results.box.mr,
        }

        # Per-class metrics if available
        if hasattr(results.box, "maps"):
            metrics["per_class_mAP50-95"] = results.box.maps.tolist()

        return metrics

    def get_model_path(self) -> str:
        """
        Get path to trained model weights.

        Returns:
            Path to best.pt
        """
        # After training, the best weights are typically at:
        # runs/<name>/weights/best.pt
        if hasattr(self.model, "trainer") and self.model.trainer:
            save_dir = Path(self.model.trainer.save_dir)
            best_path = save_dir / "weights" / "best.pt"
            if best_path.exists():
                return str(best_path)

        # Fallback: return current model path
        return str(self.model.ckpt_path) if hasattr(self.model, "ckpt_path") else ""

    def save(self, path: str) -> None:
        """
        Save model to specific path.

        Args:
            path: Output path
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.model.save(path)

    def export(self, format: str = "onnx", **kwargs: object) -> str:
        """
        Export model to different format.

        Args:
            format: Export format (onnx, torchscript, etc.)
            **kwargs: Additional export arguments

        Returns:
            Path to exported model
        """
        return self.model.export(format=format, **kwargs)


def train_model(
    data_yaml: str,
    model_size: str = "n",
    epochs: int = 100,
    batch_size: int = 16,
    project: str | None = None,
    name: str | None = None,
) -> YOLOTrainer:
    """
    Convenience function to train a YOLO model.

    Args:
        data_yaml: Path to data.yaml
        model_size: Model size
        epochs: Number of epochs
        batch_size: Batch size
        project: Project directory
        name: Run name

    Returns:
        Trained YOLOTrainer instance
    """
    trainer = YOLOTrainer(model_size=model_size)
    trainer.train(
        data_yaml=data_yaml,
        epochs=epochs,
        batch_size=batch_size,
        project=project,
        name=name,
    )
    return trainer


def train_mini_model(
    data_yaml: str,
    model_size: str = "n",
    epochs: int = 50,
    batch_size: int = 8,
    project: str | None = None,
    name: str | None = None,
) -> YOLOTrainer:
    """
    Convenience function to train a mini model for small datasets.

    Args:
        data_yaml: Path to data.yaml
        model_size: Model size
        epochs: Number of epochs
        batch_size: Batch size
        project: Project directory
        name: Run name

    Returns:
        Trained YOLOTrainer instance
    """
    trainer = YOLOTrainer(model_size=model_size)
    trainer.train_mini_model(
        data_yaml=data_yaml,
        epochs=epochs,
        batch_size=batch_size,
        project=project,
        name=name,
    )
    return trainer
