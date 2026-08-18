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
        session_name: str,
        classes: List[str],
        base_path: Optional[str] = None,
        window_handle: Optional[int] = None,
    ):
        """
        Initialize bootstrap workflow.

        Args:
            session_name: Name used for folder/model naming (e.g. "GS2Map" or "PacPinky").
            classes: Detection classes to annotate (e.g. ["PacPinky"] or ["Slimy", "SelkieJr"]).
            base_path: Base path for all data.
            window_handle: Win32 handle of the game window to capture.
        """
        self.class_name = session_name   # kept as alias — used for path/model naming
        self.classes = classes
        self.window_handle = window_handle

        # Setup paths
        self.base_path = Path(base_path or "data")

        self.raw_images_dir = self.base_path / "captures" / session_name
        self.annotations_dir = self.base_path / "captures" / f"{session_name}_labels"

        # Create directories
        for directory in [self.raw_images_dir, self.annotations_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.capturer = ScreenCapture(
            output_dir=str(self.raw_images_dir),
            window_handle=window_handle,
        )
        self.registry = get_registry()
        
        # State tracking
        self.initial_dataset_name = f"{session_name}_initial"
        self.final_dataset_name = f"{session_name}_final"
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
        print(f"  - Ctrl+Click: Remove box under cursor")
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
    
    def preannotate_with_model(
        self,
        model_path: str,
        images_dir: Path,
        labels_dir: Path,
        target_classes: List[str],
        conf: float = 0.35,
        iou: float = 0.45,
    ) -> None:
        """
        Run a model on images_dir and MERGE its detections for target_classes
        into the existing label files in labels_dir.

        Existing labels are preserved — only new boxes for the target classes
        are appended.  Class IDs are remapped from the model's own numbering
        to the session's CLASSES list.

        Args:
            model_path: Path to the model to use (e.g. the global production model).
            images_dir: Directory of images to run inference on.
            labels_dir: Directory where label .txt files live (existing labels kept).
            target_classes: Only detections for these class names are written.
            conf: Confidence threshold.
            iou: IOU threshold for NMS.
        """
        from ultralytics import YOLO

        labels_dir.mkdir(parents=True, exist_ok=True)
        model = YOLO(model_path)
        model_names: dict = model.names  # {id: class_name}

        # Map model class IDs → session class IDs for target classes only
        id_map: dict[int, int] = {}
        for model_id, class_name in model_names.items():
            if class_name in target_classes and class_name in self.classes:
                id_map[model_id] = self.classes.index(class_name)

        if not id_map:
            print(
                f"  None of {target_classes} found in model "
                f"(available: {list(model_names.values())})."
            )
            return

        image_files = sorted(
            f for f in images_dir.iterdir()
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp']
        )
        print(f"  Running on {len(image_files)} images (conf={conf}, target={target_classes})…")

        target_session_ids = set(id_map.values())
        added_total = 0

        for img_path in image_files:
            results = model(str(img_path), conf=conf, iou=iou, verbose=False)

            new_lines = []
            for box in results[0].boxes:
                model_id = int(box.cls)
                if model_id not in id_map:
                    continue
                session_id = id_map[model_id]
                x, y, w, h = box.xywhn[0].tolist()
                new_lines.append(f"{session_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")

            label_path = labels_dir / f"{img_path.stem}.txt"

            # Keep existing lines for OTHER classes, replace target-class lines.
            # This makes the function idempotent: running it twice gives the same result.
            kept_lines = []
            if label_path.exists():
                for line in label_path.read_text().splitlines():
                    parts = line.strip().split()
                    if parts and int(parts[0]) not in target_session_ids:
                        kept_lines.append(line.strip())

            all_lines = kept_lines + new_lines
            if all_lines:
                with open(label_path, 'w') as f:
                    f.write('\n'.join(all_lines) + '\n')
                added_total += len(new_lines)

        print(f"  Done — wrote {added_total} boxes across {len(image_files)} images.")

    def reannotate_extended_samples(self) -> None:
        """
        Re-open the annotation GUI on already-captured extended images so the
        user can add new class boxes to existing annotations without re-capturing.
        Existing labels are loaded; user just draws boxes for the missing classes.
        """
        if not hasattr(self, 'extended_images_dir') or not self.extended_images_dir.exists():
            print("No extended images found — skipping extended re-annotation.")
            return

        labels_dir = getattr(self, 'extended_annotations_dir', None) or (
            self.base_path / "captures" / f"{self.class_name}_extended_labels"
        )

        print(f"\n{'='*60}")
        print(f"RE-ANNOTATE EXTENDED IMAGES")
        print(f"{'='*60}")
        print(f"Add boxes for new classes — existing boxes are already loaded.")
        print(f"Controls: A/D = prev/next   Ctrl+Click = remove box   Del = delete last box   Ctrl+S = save")
        print(f"{'='*60}\n")

        run_annotator(
            images_dir=str(self.extended_images_dir),
            labels_dir=str(labels_dir),
            classes=self.classes,
            mode="annotate",
        )
        self.extended_annotations_dir = labels_dir
        print("\nRe-annotation complete!")

    def train_mini_model(self, model_size: str = 'n') -> str:
        """
        Train mini model on initial samples.

        Args:
            model_size: Model size

        Returns:
            Path to trained model
        """
        print(f"\n{'='*60}")
        print(f"TRAINING MINI MODEL")
        print(f"{'='*60}\n")

        images_dir = self.raw_images_dir
        labels_dir = self.annotations_dir
        
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
    
    def verify_mini_model(
        self,
        conf: float = 0.15,
        iou: float = 0.45,
    ) -> tuple:
        """
        Open live inference viewer so the user can validate the mini model
        and tune thresholds before the active-learning phase.

        Returns:
            (conf, iou) chosen by the user — passed to predict_and_verify.
        """
        if not self.mini_model_path:
            raise ValueError("Mini model not trained yet. Run train_mini_model() first.")
        if not self.window_handle:
            raise ValueError("No window handle set — cannot open live viewer.")

        from ..gui import run_live_inference

        print(f"\n{'='*60}")
        print(f"LIVE INFERENCE CHECK")
        print(f"{'='*60}")
        print(f"Adjust conf/IOU sliders until detections look correct.")
        print(f"Click 'Proceed' when satisfied.\n")

        chosen_conf, chosen_iou = run_live_inference(
            model_path=self.mini_model_path,
            window_handle=self.window_handle,
            classes=self.classes,
            conf=conf,
            iou=iou,
        )
        print(f"Proceeding with conf={chosen_conf:.2f}, iou={chosen_iou:.2f}")
        return chosen_conf, chosen_iou

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
        extended_dir = self.base_path / "captures" / f"{self.class_name}_extended"
        extended_dir.mkdir(parents=True, exist_ok=True)
        
        capturer = ScreenCapture(output_dir=str(extended_dir), window_handle=self.window_handle)
        captured = capturer.capture_burst(
            count=count,
            prefix=f"{self.class_name}_extended"
        )
        
        self.extended_images_dir = extended_dir
        print(f"\nCaptured {len(captured)} images to {extended_dir}")
        return len(captured)
    
    def predict_and_verify(
        self,
        conf: float = 0.15,
        iou: float = 0.45,
        retrain_every: int = 0,
        model_size: str = 'n',
        skip_preannotation: bool = False,
    ) -> None:
        """
        Run predictions on extended samples and open GUI for verification.

        Args:
            conf: Confidence threshold for pre-annotation (from verify_mini_model).
            iou: IOU threshold for NMS (from verify_mini_model).
            retrain_every: Re-train after every N verified images (0 = disabled).
            model_size: Model size for intermediate retrains.
            skip_preannotation: Keep existing label files instead of re-running the
                mini model over the extended images. Use when resuming a crashed
                verify session so already-verified labels are not overwritten.
        """
        if not self.mini_model_path:
            raise ValueError("Mini model not trained yet. Run train_mini_model() first.")
        if not hasattr(self, 'extended_images_dir'):
            raise ValueError("Extended samples not captured. Run capture_extended_samples() first.")

        predictions_dir = self.base_path / "captures" / f"{self.class_name}_extended_labels"
        predictions_dir.mkdir(parents=True, exist_ok=True)

        if skip_preannotation:
            existing = len(list(predictions_dir.glob('*.txt')))
            print(f"\n[skip] Pre-annotation — keeping {existing} existing label files in {predictions_dir}")
        else:
            print(f"\n{'='*60}")
            print(f"Running predictions on extended samples (conf={conf:.2f}, iou={iou:.2f})…")
            print(f"{'='*60}\n")

            inference = YOLOInference(self.mini_model_path, confidence_threshold=conf, iou_threshold=iou)
            total = inference.batch_predict_and_save(
                images_dir=str(self.extended_images_dir),
                output_labels_dir=str(predictions_dir),
            )
            print(f"\nGenerated {total} pre-annotations across {len(list(self.extended_images_dir.glob('*')))} images")

        print(f"\n{'='*60}")
        print(f"Opening verification GUI…  (Enter = accept & next, A/D = prev/next, "
              f"Ctrl+Click = remove box, Del = delete last box)")
        if retrain_every > 0:
            print(f"  Model retrains every {retrain_every} verified images → live viewer → re-annotates remaining.")
        print(f"{'='*60}\n")

        compute_fn, post_fn = self._make_retrain_fns(
            predictions_dir=predictions_dir,
            conf=conf,
            iou=iou,
            model_size=model_size,
        ) if retrain_every > 0 else (None, None)

        run_annotator(
            images_dir=str(self.extended_images_dir),
            labels_dir=str(predictions_dir),
            classes=self.classes,
            mode="verify",
            retrain_every=retrain_every,
            retrain_compute_fn=compute_fn,
            retrain_post_fn=post_fn,
        )

        self._merge_annotations(predictions_dir)
        print("Verification complete!")

    def _make_retrain_fns(
        self,
        predictions_dir: Path,
        conf: float,
        iou: float,
        model_size: str,
    ):
        """
        Returns (compute_fn, post_fn) for iterative retraining.

        compute_fn(verified_count) -> str
            Runs in a background thread.  Assembles Phase 1 + verified extended data,
            quick-retrains, returns the new model path.

        post_fn(new_model_path, verified_count)
            Runs on the main thread after compute_fn.  Opens the live inference viewer
            (nested event loop so it's interactive) so the user can tune thresholds,
            then re-annotates remaining images with the improved model + chosen thresholds.
        """
        all_extended = sorted(
            f for f in self.extended_images_dir.iterdir()
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp']
        )
        state = {'iter': 0, 'conf': conf, 'iou': iou}

        def compute_fn(verified_count: int) -> str:
            state['iter'] += 1
            n = state['iter']

            print(f"\n{'='*60}")
            print(f"INTERMEDIATE RETRAIN #{n}  ({verified_count} verified + Phase 1 images)")
            print(f"{'='*60}\n")

            tmp_images = self.base_path / "datasets" / f"{self.class_name}_iter{n}" / "raw_images"
            tmp_labels = self.base_path / "datasets" / f"{self.class_name}_iter{n}" / "raw_labels"
            tmp_images.mkdir(parents=True, exist_ok=True)
            tmp_labels.mkdir(parents=True, exist_ok=True)

            for img in self.raw_images_dir.iterdir():
                if img.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp']:
                    lbl = self.annotations_dir / f"{img.stem}.txt"
                    if lbl.exists():
                        shutil.copy(img, tmp_images / img.name)
                        shutil.copy(lbl, tmp_labels / lbl.name)

            for img in all_extended[:verified_count]:
                lbl = predictions_dir / f"{img.stem}.txt"
                if lbl.exists():
                    shutil.copy(img, tmp_images / img.name)
                    shutil.copy(lbl, tmp_labels / lbl.name)

            n_train = len(list(tmp_images.glob('*.*')))
            if n_train < 5:
                print(f"Only {n_train} training images — skipping retrain.")
                return ""

            dataset = create_dataset(
                name=f"{self.class_name}_iter{n}",
                classes=self.classes,
                images_dir=str(tmp_images),
                labels_dir=str(tmp_labels),
            )
            trainer = YOLOTrainer(model_size=model_size)
            trainer.train_mini_model(
                data_yaml=dataset.get_data_yaml_path(),
                name=f"{self.class_name}_iter{n}",
            )
            new_path = trainer.get_model_path()
            if new_path:
                print(f"\nRetrain #{n} complete: {new_path}")
            else:
                print(f"\nRetrain #{n}: training produced no model, keeping previous.")
            return new_path or ""

        def post_fn(new_model_path: str, verified_count: int) -> None:
            self.mini_model_path = new_model_path

            # Show live viewer so user can tune thresholds for the improved model
            if self.window_handle:
                from ..gui.live_inference import run_live_inference_nested
                print(f"\nOpening live viewer — adjust thresholds for the improved model, then Proceed.")
                new_conf, new_iou = run_live_inference_nested(
                    model_path=new_model_path,
                    window_handle=self.window_handle,
                    classes=self.classes,
                    conf=state['conf'],
                    iou=state['iou'],
                )
                state['conf'] = new_conf
                state['iou'] = new_iou
            else:
                new_conf, new_iou = state['conf'], state['iou']

            # Re-annotate remaining images with the improved model + new thresholds
            remaining = all_extended[verified_count:]
            if remaining:
                print(f"\nRe-annotating {len(remaining)} remaining images "
                      f"(conf={new_conf:.2f}, iou={new_iou:.2f})…")
                inference = YOLOInference(new_model_path,
                                         confidence_threshold=new_conf,
                                         iou_threshold=new_iou)
                for img in remaining:
                    lbl = predictions_dir / f"{img.stem}.txt"
                    try:
                        inference.save_predictions_yolo_format(str(img), str(lbl), conf=new_conf)
                    except Exception as e:
                        print(f"  Warning: {img.name}: {e}")
                print(f"Done — {len(remaining)} images updated.")
            else:
                print("All images already verified.")

        return compute_fn, post_fn
    
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
        combined_images = self.base_path / "datasets" / f"{self.class_name}_combined" / "images"
        combined_labels = self.base_path / "datasets" / f"{self.class_name}_combined" / "labels"
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
        
        # Use the class name as the bot config key.
        # "All" is reserved for the global model that covers every class.
        config_key = self.classes[0] if len(self.classes) == 1 else self.class_name
        print(f"Model exported to production: {prod_path}")
        print(f"\nThis model detects: {self.classes}")
        print(f'Add to bot config:  "models_path": {{"{config_key}": "{prod_path}"}}')
        print('(Use "All" only once you have a global model trained on all classes.)')
        
        return prod_path

    def cleanup_intermediate(self) -> None:
        """
        Remove intermediate derived files — never touches your source data.

        KEEPS (never removed):
          data/captures/                    ← all your raw screenshots + annotations
          data/datasets/{session}_final/    ← the complete YOLO-ready training set
          data/models/registry/             ← version history
          data/models/production/           ← deployed models the bot loads
          data/models/runs/{session}_final/ ← final training metrics, curves, confusion matrix

        REMOVES (derived / temporary):
          data/datasets/{session}_initial/  ← early split of Phase 1 captures (can be regenerated)
          data/datasets/{session}_combined/ ← temp merge dir (already packed into _final)
          data/datasets/{session}_iter*/    ← intermediate retrain datasets
          data/models/runs/{session}_mini/  ← mini-model training artifacts
          data/models/runs/{session}_iter*/ ← intermediate retrain artifacts
        """
        print(f"\n{'='*60}")
        print("CLEANUP")
        print(f"{'='*60}\n")

        datasets_base = self.base_path / "datasets"
        runs_base = Path("data/models/runs")

        patterns_to_remove = [
            datasets_base / self.initial_dataset_name,
            datasets_base / f"{self.class_name}_combined",
        ]
        # iter* datasets and runs
        for d in datasets_base.glob(f"{self.class_name}_iter*"):
            patterns_to_remove.append(d)
        for d in runs_base.glob(f"{self.class_name}_mini*"):
            patterns_to_remove.append(d)
        for d in runs_base.glob(f"{self.class_name}_iter*"):
            patterns_to_remove.append(d)

        removed = []
        for d in patterns_to_remove:
            if d.exists():
                shutil.rmtree(d)
                removed.append(str(d))

        if removed:
            for r in removed:
                print(f"  removed  {r}")
        else:
            print("  nothing to clean up.")


def train_global_production_model(
    dataset_paths: List[str],
    name: str = "global",
    model_size: str = 'n',
    base_path: str = "data",
) -> str:
    """
    Merge all specified YOLO datasets and train a single global production model
    that detects every class across all datasets.

    Args:
        dataset_paths: Paths to YOLO-format dataset directories (each must contain data.yaml).
        name: Name for the merged dataset and model (used as folder name).
        model_size: YOLO model size ('n', 's', 'm', 'l', 'x').
        base_path: Root data directory.

    Returns:
        Production model directory path — set as "models_path": {"All": <returned_path>} in bot config.
    """
    from ..dataset_manager import merge_datasets

    print(f"\n{'='*60}")
    print("GLOBAL MODEL RETRAIN")
    print(f"{'='*60}")
    print(f"Merging {len(dataset_paths)} datasets…\n")

    dataset = merge_datasets(dataset_paths, name=name)
    stats = dataset.get_stats()
    print(f"Merged dataset: {stats['total_instances']} instances across {len(stats['class_counts'])} classes")
    print(f"  Classes: {list(stats['class_counts'].keys())}")

    print(f"\nTraining global model (size={model_size})…")
    trainer = YOLOTrainer(model_size=model_size)
    trainer.train(data_yaml=dataset.get_data_yaml_path(), name=name)

    model_path = trainer.get_model_path()
    if not model_path:
        raise RuntimeError("Global model training produced no output.")

    # Export to production/{name}/weights/best.pt
    prod_dir = Path(base_path) / "models" / "production" / name / "weights"
    prod_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(model_path, prod_dir / "best.pt")

    prod_path = str(prod_dir.parent)
    print(f"\n{'='*60}")
    print(f"Global model exported: {prod_path}")
    print(f'Bot config:  "models_path": {{"All": "{prod_path}"}}')
    print(f"{'='*60}\n")

    return prod_path
