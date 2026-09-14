"""Model registry and versioning system."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import config


class ModelRegistry:
    """Model registry for tracking trained models."""

    def __init__(self, base_path: str | None = None):
        """
        Initialize model registry.

        Args:
            base_path: Base path for model storage
        """
        self.base_path = Path(
            base_path or config.get("registry.models_path", "data/models/registry")
        )
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.production_path = Path(
            config.get("registry.production_path", "data/models/production")
        )
        self.production_path.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.base_path / config.get(
            "registry.metadata_file", "model_registry.json"
        )

        # Load existing registry
        self._registry = self._load_registry()

    def _load_registry(self) -> dict:
        """Load registry from file."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        return {"models": []}

    def _save_registry(self) -> None:
        """Save registry to file."""
        with open(self.metadata_file, "w") as f:
            json.dump(self._registry, f, indent=2)

    def register_model(
        self,
        name: str,
        model_path: str,
        dataset_name: str,
        metrics: dict[str, float],
        hyperparameters: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> str:
        """
        Register a trained model.

        Args:
            name: Model name
            model_path: Path to model file
            dataset_name: Name of dataset used for training
            metrics: Training/validation metrics
            hyperparameters: Training hyperparameters
            notes: Additional notes

        Returns:
            Model ID (version)
        """
        model_path = Path(model_path)

        if not model_path.exists():
            raise ValueError(f"Model file not found: {model_path}")

        # Generate version
        existing_versions = [
            m["version"] for m in self._registry["models"] if m["name"] == name
        ]

        if existing_versions:
            latest_version = max(existing_versions)
            version = latest_version + 1
        else:
            version = 1

        # Create model directory
        model_dir = self.base_path / f"{name}_v{version}"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Copy model file
        dest_model_path = model_dir / "model.pt"
        shutil.copy(model_path, dest_model_path)

        # Create metadata
        metadata = {
            "name": name,
            "version": version,
            "model_id": f"{name}_v{version}",
            "model_path": str(dest_model_path),
            "dataset_name": dataset_name,
            "metrics": metrics,
            "hyperparameters": hyperparameters or {},
            "notes": notes or "",
            "registered_at": datetime.now().isoformat(),
            "is_production": False,
        }

        # Save metadata to model directory
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Add to registry
        self._registry["models"].append(metadata)
        self._save_registry()

        print(f"Registered model: {metadata['model_id']}")
        return metadata["model_id"]

    def get_model(self, model_id: str) -> dict | None:
        """
        Get model metadata by ID.

        Args:
            model_id: Model ID (e.g., "fire_demon_v1")

        Returns:
            Model metadata or None
        """
        for model in self._registry["models"]:
            if model["model_id"] == model_id:
                return model
        return None

    def get_latest_model(self, name: str) -> dict | None:
        """
        Get latest version of model by name.

        Args:
            name: Model name

        Returns:
            Latest model metadata or None
        """
        models = [m for m in self._registry["models"] if m["name"] == name]
        if not models:
            return None

        return max(models, key=lambda m: m["version"])

    def list_models(self, name: str | None = None) -> list[dict]:
        """
        List all models or filter by name.

        Args:
            name: Optional model name filter

        Returns:
            List of model metadata
        """
        if name:
            return [m for m in self._registry["models"] if m["name"] == name]
        return self._registry["models"].copy()

    def promote_to_production(self, model_id: str) -> str:
        """
        Promote model to production by copying it.

        Args:
            model_id: Model ID to promote

        Returns:
            Production model path
        """
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model not found: {model_id}")

        # Demote any existing production model with same name
        for m in self._registry["models"]:
            if m["name"] == model["name"] and m["is_production"]:
                m["is_production"] = False

        # Copy to production in bot-compatible directory structure
        # Bot expects: {path}/weights/best.pt (see InGameDetectionVisuals.register_models)
        src_path = Path(model["model_path"])
        dest_dir = self.production_path / model["name"] / "weights"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / "best.pt"

        shutil.copy(src_path, dest_path)

        # Update metadata — production_path points to the model directory (not the .pt)
        model["is_production"] = True
        model["production_path"] = str(dest_dir.parent)
        model["promoted_at"] = datetime.now().isoformat()

        self._save_registry()

        prod_model_dir = str(dest_dir.parent)
        print(f"Promoted {model_id} to production: {prod_model_dir}")
        return prod_model_dir

    def get_production_model(self, name: str) -> dict | None:
        """
        Get production model by name.

        Args:
            name: Model name

        Returns:
            Production model metadata or None
        """
        for model in self._registry["models"]:
            if model["name"] == name and model["is_production"]:
                return model
        return None

    def compare_models(self, model_ids: list[str]) -> dict:
        """
        Compare metrics across multiple models.

        Args:
            model_ids: List of model IDs to compare

        Returns:
            Comparison dictionary
        """
        comparison = {"models": [], "metrics_comparison": {}}

        models = [self.get_model(mid) for mid in model_ids]
        models = [m for m in models if m is not None]

        if not models:
            return comparison

        # Collect all metric keys
        all_metrics = set()
        for model in models:
            all_metrics.update(model["metrics"].keys())

        # Build comparison
        for metric in all_metrics:
            comparison["metrics_comparison"][metric] = []
            for model in models:
                comparison["metrics_comparison"][metric].append(
                    {
                        "model_id": model["model_id"],
                        "value": model["metrics"].get(metric, None),
                    }
                )

        comparison["models"] = [
            {
                "model_id": m["model_id"],
                "version": m["version"],
                "dataset": m["dataset_name"],
                "registered_at": m["registered_at"],
            }
            for m in models
        ]

        return comparison

    def delete_model(self, model_id: str, delete_files: bool = False) -> bool:
        """
        Delete model from registry.

        Args:
            model_id: Model ID to delete
            delete_files: Whether to delete model files

        Returns:
            True if deleted, False if not found
        """
        model = self.get_model(model_id)
        if not model:
            return False

        # Remove from registry
        self._registry["models"] = [
            m for m in self._registry["models"] if m["model_id"] != model_id
        ]
        self._save_registry()

        # Delete files if requested
        if delete_files:
            model_dir = Path(model["model_path"]).parent
            if model_dir.exists():
                shutil.rmtree(model_dir)

        print(f"Deleted model: {model_id}")
        return True


# Global registry instance
_registry_instance: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """
    Get global model registry instance.

    Returns:
        ModelRegistry instance
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance
