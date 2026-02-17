"""Tests for ML Training package - basic unit tests."""

import unittest
from pathlib import Path
import tempfile
import shutil
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestConfigStructure(unittest.TestCase):
    """Test configuration structure."""
    
    def test_config_file_exists(self):
        """Test that config file exists."""
        config_path = Path(__file__).parent.parent.parent / "ml_training" / "config" / "settings.yaml"
        self.assertTrue(config_path.exists(), "Config file should exist")
    
    def test_package_structure(self):
        """Test that all required modules exist."""
        base_path = Path(__file__).parent.parent.parent / "ml_training"
        
        # Check main directories
        self.assertTrue((base_path / "config").exists())
        self.assertTrue((base_path / "dataset_manager").exists())
        self.assertTrue((base_path / "model_manager").exists())
        self.assertTrue((base_path / "gui").exists())
        self.assertTrue((base_path / "workflows").exists())
        self.assertTrue((base_path / "examples").exists())
        
        # Check key files
        self.assertTrue((base_path / "__init__.py").exists())
        self.assertTrue((base_path / "README.md").exists())
        self.assertTrue((base_path / "requirements.txt").exists())
        self.assertTrue((base_path / ".gitignore").exists())


class TestDirectoryStructure(unittest.TestCase):
    """Test directory structure requirements."""
    
    def test_gitignore_exists(self):
        """Test .gitignore exists."""
        gitignore = Path(__file__).parent.parent.parent / "ml_training" / ".gitignore"
        self.assertTrue(gitignore.exists())
        
        # Check it contains data directories
        content = gitignore.read_text()
        self.assertIn("data/", content)
    
    def test_requirements_has_dependencies(self):
        """Test requirements.txt has required dependencies."""
        req_file = Path(__file__).parent.parent.parent / "ml_training" / "requirements.txt"
        self.assertTrue(req_file.exists())
        
        content = req_file.read_text()
        required_deps = ['ultralytics', 'torch', 'opencv-python', 'PyQt6', 'PyYAML']
        
        for dep in required_deps:
            self.assertIn(dep, content, f"{dep} should be in requirements.txt")
    
    def test_all_modules_have_init(self):
        """Test all modules have __init__.py."""
        base_path = Path(__file__).parent.parent.parent / "ml_training"
        
        modules = ['config', 'dataset_manager', 'model_manager', 'gui', 'workflows']
        
        for module in modules:
            init_file = base_path / module / "__init__.py"
            self.assertTrue(init_file.exists(), f"{module}/__init__.py should exist")
    
    def test_all_required_files_exist(self):
        """Test all required module files exist."""
        base_path = Path(__file__).parent.parent.parent / "ml_training"
        
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
            self.assertTrue(full_path.exists(), f"{file_path} should exist")


class TestExamplesExist(unittest.TestCase):
    """Test that example files exist."""
    
    def test_example_workflow_exists(self):
        """Test example workflow file exists."""
        example_file = Path(__file__).parent.parent.parent / "ml_training" / "examples" / "example_workflow.py"
        self.assertTrue(example_file.exists())
        
        # Check it has example functions
        content = example_file.read_text()
        self.assertIn("example_bootstrap_workflow", content)
        self.assertIn("example_screen_capture", content)


class TestDocumentation(unittest.TestCase):
    """Test documentation exists."""
    
    def test_readme_has_sections(self):
        """Test README has required sections."""
        readme = Path(__file__).parent.parent.parent / "ml_training" / "README.md"
        self.assertTrue(readme.exists())
        
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
            self.assertIn(section, content, f"README should have {section} section")


if __name__ == '__main__':
    unittest.main()
