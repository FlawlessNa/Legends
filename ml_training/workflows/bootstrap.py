"""Bootstrap workflow for training new detection classes."""

import shutil
from pathlib import Path
from typing import List, Optional

from ..config import config, SUPPORTED_IMAGE_EXTENSIONS
from ..dataset_manager import (
    ScreenCapture,
    YOLODataset,
    create_dataset,
)
from ..gui import run_annotator
from ..model_manager import (
    ModelRegistry,
    YOLOInference,
    YOLOTrainer,
    get_registry,
)


class BootstrapNewClass:
    """Complete workflow for bootstrapping a new detection class."""
    
    def __init__(
        self,
        class_name: str,
        additional_classes: Optional[List[str]] = None,
        base_path: Optional[str] = None
    ):
        """
        Initialize bootstrap workflow.
        
        Args:
            class_name: Name of the new class to train
            additional_classes: Other classes to train alongside (for multi-class models)
            base_path: Base path for all data
        """
        self.class_name = class_name
        self.classes = [class_name] + (additional_classes or [])
        
        # Setup paths
        self.base_path = Path(base_path or "ml_training/data")
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.raw_images_dir = self.base_path / "raw_images" / class_name
        self.annotations_dir = self.base_path / "annotations" / class_name
        self.augmented_images_dir = self.base_path / "augmented" / class_name / "images"
        self.augmented_labels_dir = self.base_path / "augmented" / class_name / "labels"
        
        # Create directories
        for directory in [
            self.raw_images_dir,
            self.annotations_dir,
            self.augmented_images_dir,
            self.augmented_labels_dir
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.capturer = ScreenCapture(output_dir=str(self.raw_images_dir))
        self.registry = get_registry()
        
        # State tracking
        self.initial_dataset_name = f"{class_name}_initial"
        self.final_dataset_name = f"{class_name}_final"
        self.mini_model_path: Optional[str] = None
        self.final_model_path: Optional[str] = None
    
    def capture_initial_samples(self, count: Optional[int] = None) -> int:
        """
        Capture initial sample images.
        
        Args:
            count: Number of images to capture
            
        Returns:
            Number of images captured
        """
        count = count or config.get('bootstrap.initial_samples', 10)
        
        print(f"\n{'='*60}")
        print(f"PHASE 1: INITIAL BOOTSTRAP")
        print(f"{'='*60}")
        print(f"Capturing {count} initial samples for '{self.class_name}'...")
        print(f"Make sure the game window is visible!\n")
        
        captured = self.capturer.capture_burst(
            count=count,
            prefix=f"{self.class_name}_initial"
        )
        
        print(f"\nCaptured {len(captured)} images to {self.raw_images_dir}")
        return len(captured)
    
    def annotate_initial_samples(self) -> None:
        """
        Open GUI to annotate initial samples.
        """
        print(f"\n{'='*60}")
        print(f"Opening annotation GUI...")
        print(f"Draw bounding boxes around '{self.class_name}' instances")
        print(f"Controls:")
        print(f"  - Click and drag to draw box")
        print(f"  - A/D: Previous/Next image")
        print(f"  - Del: Delete last box")
        print(f"  - Ctrl+S: Save")
        print(f"Close the window when done.")
        print(f"{'='*60}\n")
        
        run_annotator(
            images_dir=str(self.raw_images_dir),
            labels_dir=str(self.annotations_dir),
            classes=self.classes,
            mode="annotate"
        )
        
        print(f"\nAnnotation complete!")
    
    def train_mini_model(
        self,
        augment: bool = True,
        model_size: str = 'n'
    ) -> str:
        """
        Train mini model on initial samples.
        
        Args:
            augment: Whether to augment data before training
            model_size: Model size
            
        Returns:
            Path to trained model
        """
        print(f"\n{'='*60}")
        print(f"TRAINING MINI MODEL")
        print(f"{'='*60}\n")
        
        # Note: Augmentation is optional. For small datasets, consider using
        # augmentation to increase training data. Can be done separately if needed.
        images_dir = self.raw_images_dir
        labels_dir = self.annotations_dir
        
        if augment:
            print("Note: Augmentation has been moved to an optional separate step.")
            print("The mini-model training uses aggressive augmentation parameters")
            print("during training, which is often sufficient for small datasets.\n")
        
        # Create dataset
        print("Creating YOLO dataset...")
        dataset = create_dataset(
            name=self.initial_dataset_name,
            classes=self.classes,
            images_dir=str(images_dir),
            labels_dir=str(labels_dir)
        )
        
        # Train mini model
        print("\nTraining mini model...")
        trainer = YOLOTrainer(model_size=model_size)
        
        # Use simple name without version - registry will add version
        mini_model_name = f"{self.class_name}_mini"
        
        results = trainer.train_mini_model(
            data_yaml=dataset.get_data_yaml_path(),
            name=mini_model_name
        )
        
        # Get model path
        self.mini_model_path = trainer.get_model_path()
        print(f"\nMini model trained: {self.mini_model_path}")
        
        # Evaluate
        print("\nEvaluating mini model...")
        metrics = trainer.evaluate()
        print(f"Metrics: {metrics}")
        
        # Register model
        model_id = self.registry.register_model(
            name=mini_model_name,
            model_path=self.mini_model_path,
            dataset_name=self.initial_dataset_name,
            metrics=metrics,
            hyperparameters={'model_size': model_size, 'type': 'mini'},
            notes=f"Mini model for {self.class_name} bootstrap"
        )
        
        print(f"Model registered: {model_id}")
        return self.mini_model_path
    
    def capture_extended_samples(
        self,
        count: Optional[int] = None
    ) -> int:
        """
        Capture extended sample images for active learning.
        
        Args:
            count: Number of images to capture
            
        Returns:
            Number of images captured
        """
        count = count or config.get('bootstrap.extended_samples', 100)
        
        print(f"\n{'='*60}")
        print(f"PHASE 2: ACTIVE LEARNING")
        print(f"{'='*60}")
        print(f"Capturing {count} extended samples...")
        print(f"Make sure the game window is visible!\n")
        
        # Create extended samples directory
        extended_dir = self.base_path / "raw_images" / f"{self.class_name}_extended"
        extended_dir.mkdir(parents=True, exist_ok=True)
        
        capturer = ScreenCapture(output_dir=str(extended_dir))
        captured = capturer.capture_burst(
            count=count,
            prefix=f"{self.class_name}_extended"
        )
        
        self.extended_images_dir = extended_dir
        print(f"\nCaptured {len(captured)} images to {extended_dir}")
        return len(captured)
    
    def predict_and_verify(self) -> None:
        """
        Run predictions on extended samples and open GUI for verification.
        """
        if not self.mini_model_path:
            raise ValueError("Mini model not trained yet. Run train_mini_model() first.")
        
        if not hasattr(self, 'extended_images_dir'):
            raise ValueError("Extended samples not captured. Run capture_extended_samples() first.")
        
        print(f"\n{'='*60}")
        print(f"Running predictions on extended samples...")
        print(f"{'='*60}\n")
        
        # Create predictions directory
        predictions_dir = self.base_path / "predictions" / self.class_name
        predictions_dir.mkdir(parents=True, exist_ok=True)
        
        # Run predictions
        inference = YOLOInference(self.mini_model_path)
        total_detections = inference.batch_predict_and_save(
            images_dir=str(self.extended_images_dir),
            output_labels_dir=str(predictions_dir)
        )
        
        print(f"\nGenerated predictions for {total_detections} detections")
        
        # Open verification GUI
        print(f"\n{'='*60}")
        print(f"Opening verification GUI...")
        print(f"Review and correct predictions")
        print(f"Controls:")
        print(f"  - Edit boxes by drawing new ones")
        print(f"  - Del: Delete last box")
        print(f"  - Enter: Accept and next")
        print(f"  - A/D: Previous/Next")
        print(f"Close the window when done.")
        print(f"{'='*60}\n")
        
        run_annotator(
            images_dir=str(self.extended_images_dir),
            labels_dir=str(predictions_dir),
            classes=self.classes,
            mode="verify"
        )
        
        # Merge annotations
        print(f"\nMerging annotations...")
        self._merge_annotations(predictions_dir)
        
        print(f"Verification complete!")
    
    def _merge_annotations(self, predictions_dir: Path) -> None:
        """
        Merge initial and verified annotations.
        
        Args:
            predictions_dir: Directory with verified predictions
        """
        # This could copy verified labels to final annotations directory
        # For now, we'll use them in place
        self.extended_annotations_dir = predictions_dir
    
    def train_final_model(self, model_size: str = 'n') -> str:
        """
        Train final model on complete dataset.
        
        Args:
            model_size: Model size
            
        Returns:
            Path to trained model
        """
        print(f"\n{'='*60}")
        print(f"PHASE 3: FINAL TRAINING")
        print(f"{'='*60}\n")
        
        # Combine all data
        print("Preparing final dataset...")
        
        # Create combined dataset directory
        combined_images = self.base_path / "combined" / self.class_name / "images"
        combined_labels = self.base_path / "combined" / self.class_name / "labels"
        combined_images.mkdir(parents=True, exist_ok=True)
        combined_labels.mkdir(parents=True, exist_ok=True)
        
        # Copy initial samples
        for img in self.raw_images_dir.glob('*'):
            if img.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                shutil.copy(img, combined_images / img.name)
                
                label = self.annotations_dir / f"{img.stem}.txt"
                if label.exists():
                    shutil.copy(label, combined_labels / label.name)
        
        # Copy extended samples
        if hasattr(self, 'extended_images_dir') and hasattr(self, 'extended_annotations_dir'):
            for img in self.extended_images_dir.glob('*'):
                if img.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    shutil.copy(img, combined_images / img.name)
                    
                    label = self.extended_annotations_dir / f"{img.stem}.txt"
                    if label.exists():
                        shutil.copy(label, combined_labels / label.name)
        
        # Create final dataset
        dataset = create_dataset(
            name=self.final_dataset_name,
            classes=self.classes,
            images_dir=str(combined_images),
            labels_dir=str(combined_labels)
        )
        
        print(f"Dataset stats: {dataset.get_stats()}")
        
        # Train final model
        print("\nTraining final model...")
        trainer = YOLOTrainer(model_size=model_size)
        
        # Use simple name without version - registry will add version
        final_model_name = f"{self.class_name}_final"
        
        results = trainer.train(
            data_yaml=dataset.get_data_yaml_path(),
            name=final_model_name
        )
        
        # Get model path
        self.final_model_path = trainer.get_model_path()
        print(f"\nFinal model trained: {self.final_model_path}")
        
        # Evaluate
        print("\nEvaluating final model...")
        metrics = trainer.evaluate()
        print(f"Metrics: {metrics}")
        
        # Register model
        model_id = self.registry.register_model(
            name=final_model_name,
            model_path=self.final_model_path,
            dataset_name=self.final_dataset_name,
            metrics=metrics,
            hyperparameters={'model_size': model_size, 'type': 'final'},
            notes=f"Final model for {self.class_name}"
        )
            model_path=self.final_model_path,
            dataset_name=self.final_dataset_name,
            metrics=metrics,
            hyperparameters={'model_size': model_size, 'type': 'final'},
            notes=f"Final model for {self.class_name}"
        )
        
        print(f"Model registered: {model_id}")
        return self.final_model_path
    
    def evaluate(self) -> dict:
        """
        Evaluate final model.
        
        Returns:
            Evaluation metrics
        """
        if not self.final_model_path:
            raise ValueError("Final model not trained yet.")
        
        print(f"\n{'='*60}")
        print(f"EVALUATION")
        print(f"{'='*60}\n")
        
        trainer = YOLOTrainer(base_model=self.final_model_path)
        metrics = trainer.evaluate()
        
        print("Final Model Metrics:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
        
        return metrics
    
    def export_to_production(self) -> str:
        """
        Export final model to production.
        
        Returns:
            Production model path
        """
        if not self.final_model_path:
            raise ValueError("Final model not trained yet.")
        
        print(f"\n{'='*60}")
        print(f"EXPORTING TO PRODUCTION")
        print(f"{'='*60}\n")
        
        # Get model ID from registry - search by the base name pattern
        final_model_base_name = f"{self.class_name}_final"
        models = self.registry.list_models(name=final_model_base_name)
        final_models = [m for m in models if m.get('hyperparameters', {}).get('type') == 'final']
        
        if not final_models:
            raise ValueError("Final model not found in registry")
        
        latest_model = max(final_models, key=lambda m: m['version'])
        
        # Promote to production
        prod_path = self.registry.promote_to_production(latest_model['model_id'])
        
        print(f"Model exported to production: {prod_path}")
        print(f"\nYou can now use this model in your botting configuration!")
        
        return prod_path
