"""Configuration loader for ML Training package."""

from pathlib import Path
from typing import Any, ClassVar

import yaml

# Supported image file extensions
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"]
SUPPORTED_IMAGE_PATTERNS = ["*.jpg", "*.jpeg", "*.png", "*.bmp"]


class Config:
    """Configuration manager for ML Training package."""

    _instance: Config | None = None
    _config: ClassVar[dict[str, Any]] = {}

    def __new__(cls):
        """Singleton pattern to ensure only one config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration."""
        if not self._config:
            self.load()

    def load(self, config_path: str | None = None) -> None:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config file. If None, uses default location.
        """
        if config_path is None:
            # Default config path relative to this file
            config_dir = Path(__file__).parent
            config_path = config_dir / "settings.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key (supports dot notation like 'model.base_model')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by key.

        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split(".")
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, config_path: str | None = None) -> None:
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save config. If None, uses default location.
        """
        if config_path is None:
            config_dir = Path(__file__).parent
            config_path = config_dir / "settings.yaml"

        config_path = Path(config_path)
        with open(config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> dict[str, Any]:
        """
        Get full configuration as dictionary.

        Returns:
            Configuration dictionary
        """
        return self._config.copy()

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dictionary-style setting."""
        self.set(key, value)


# Global config instance
config = Config()


def get_config() -> Config:
    """
    Get global configuration instance.

    Returns:
        Config instance
    """
    return config


def reload_config(config_path: str | None = None) -> None:
    """
    Reload configuration from file.

    Args:
        config_path: Path to config file
    """
    config.load(config_path)
