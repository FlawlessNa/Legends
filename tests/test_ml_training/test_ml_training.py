"""Tests for ML Training package - basic unit tests."""

from pathlib import Path

import pytest


@pytest.fixture
def base_path() -> Path:
    return Path(__file__).parent.parent.parent / "ml_training"


# --- configuration structure --------------------------------------------------


def test_config_file_exists(base_path):
    """Test that config file exists."""
    config_path = base_path / "config" / "settings.yaml"
    assert config_path.exists(), "Config file should exist"


def test_package_structure(base_path):
    """Test that all required modules exist."""
    # Check main directories
    assert (base_path / "config").exists()
    assert (base_path / "dataset_manager").exists()
    assert (base_path / "model_manager").exists()
    assert (base_path / "gui").exists()
    assert (base_path / "workflows").exists()
    assert (base_path / "examples").exists()

    # Check key files
    assert (base_path / "__init__.py").exists()
    assert (base_path / "README.md").exists()
    assert (base_path / "requirements.txt").exists()
    assert (base_path / ".gitignore").exists()


# --- directory structure ------------------------------------------------------


def test_gitignore_exists(base_path):
    """Test .gitignore exists."""
    gitignore = base_path / ".gitignore"
    assert gitignore.exists()

    # Check it contains data directories
    content = gitignore.read_text()
    assert "data/" in content


def test_requirements_has_dependencies(base_path):
    """Test requirements.txt has required dependencies."""
    req_file = base_path / "requirements.txt"
    assert req_file.exists()

    content = req_file.read_text()
    required_deps = ["ultralytics", "torch", "opencv-python", "PyQt6", "PyYAML"]

    for dep in required_deps:
        assert dep in content, f"{dep} should be in requirements.txt"


def test_all_modules_have_init(base_path):
    """Test all modules have __init__.py."""
    modules = ["config", "dataset_manager", "model_manager", "gui", "workflows"]

    for module in modules:
        init_file = base_path / module / "__init__.py"
        assert init_file.exists(), f"{module}/__init__.py should exist"


def test_all_required_files_exist(base_path):
    """Test all required module files exist."""
    required_files = [
        "config/config.py",
        "config/settings.yaml",
        "dataset_manager/capture.py",
        "dataset_manager/dataset.py",
        "dataset_manager/augmentation.py",
        "model_manager/trainer.py",
        "model_manager/inference.py",
        "model_manager/versioning.py",
        "gui/annotator.py",
        "workflows/bootstrap.py",
        "examples/example_workflow.py",
    ]

    for file_path in required_files:
        full_path = base_path / file_path
        assert full_path.exists(), f"{file_path} should exist"


# --- examples -----------------------------------------------------------------


def test_example_workflow_exists(base_path):
    """Test example workflow file exists."""
    example_file = base_path / "examples" / "example_workflow.py"
    assert example_file.exists()

    # Check it has example functions
    content = example_file.read_text()
    assert "example_bootstrap_workflow" in content
    assert "example_screen_capture" in content


# --- documentation ------------------------------------------------------------


def test_readme_has_sections(base_path):
    """Test README has required sections."""
    readme = base_path / "README.md"
    assert readme.exists()

    content = readme.read_text()

    # Check for key sections
    required_sections = [
        "Installation",
        "Quick Start",
        "Bootstrap",
        "Configuration",
        "Examples",
    ]

    for section in required_sections:
        assert section in content, f"README should have {section} section"
