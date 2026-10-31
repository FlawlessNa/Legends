"""`publish_models.py` carries a model's recipe into the manifest; `fetch_models.py` writes it back."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from pytest_mock import MockerFixture

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

RECIPE = {
    "map_id": 100,
    "map_name": "Field",
    "classes": ["Snail", "Slime", "Character"],
}


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publish(tmp_path: Path, mocker: MockerFixture) -> ModuleType:
    module = load("publish_models")
    mocker.patch.object(module, "ROOT", str(tmp_path))
    mocker.patch.object(module, "PRODUCTION", str(tmp_path / "production"))
    mocker.patch.object(module, "MANIFEST", str(tmp_path / "models.manifest.json"))
    return module


def make_model(production: Path, name: str, recipe: dict | None = None) -> None:
    (production / name / "weights").mkdir(parents=True)
    (production / name / "weights" / "best.pt").write_bytes(name.encode())
    if recipe is not None:
        (production / name / "recipe.json").write_text(json.dumps(recipe))


def test_a_recipe_goes_into_the_entry_with_its_classes_and_a_description(
    publish: ModuleType, tmp_path: Path
) -> None:
    make_model(tmp_path / "production", "field", RECIPE)
    models = publish.discover()
    publish.carry_over_docs(models, [])
    (entry,) = models
    assert entry["recipe"] == RECIPE
    assert entry["classes"] == RECIPE["classes"]
    assert entry["description"] == (
        "Synthetic model for Field (100): Snail, Slime, Character."
    )


def test_classes_come_from_the_recipe_but_a_written_description_stays(
    publish: ModuleType, tmp_path: Path
) -> None:
    make_model(tmp_path / "production", "field", RECIPE)
    models = publish.discover()
    previous = [{"name": "field", "description": "Mine.", "classes": ["Old"]}]
    publish.carry_over_docs(models, previous)
    assert models[0]["classes"] == RECIPE["classes"]
    assert models[0]["description"] == "Mine."


def test_an_entry_without_a_recipe_is_as_before(
    publish: ModuleType, tmp_path: Path
) -> None:
    make_model(tmp_path / "production", "global")
    models = publish.discover()
    publish.carry_over_docs(
        models, [{"name": "global", "description": "D", "classes": ["A"]}]
    )
    assert "recipe" not in models[0]
    assert (models[0]["description"], models[0]["classes"]) == ("D", ["A"])


def test_main_writes_the_recipe_into_the_manifest_with_gh_stubbed(
    publish: ModuleType, tmp_path: Path, mocker: MockerFixture
) -> None:
    make_model(tmp_path / "production", "field", RECIPE)
    (tmp_path / "models.manifest.json").write_text(
        json.dumps({"repo": "o/r", "release_tag": "t", "models": []})
    )
    mocker.patch.object(publish.shutil, "which", return_value="gh")
    gh = mocker.patch.object(
        publish,
        "run",
        return_value=subprocess.CompletedProcess([], 0, "", ""),
    )
    mocker.patch("sys.argv", ["publish_models.py"])
    assert publish.main() == 0
    assert all(call.args[0][0] == "gh" for call in gh.call_args_list)
    written = json.loads((tmp_path / "models.manifest.json").read_text())
    assert written["models"][0]["recipe"] == RECIPE
    assert not any(k.startswith("_") for k in written["models"][0])


def test_fetch_writes_the_recipe_beside_the_weights(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    fetch = load("fetch_models")
    mocker.patch.object(fetch, "ROOT", str(tmp_path))
    weights = b"weights"

    def fake_gh(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        (Path(cmd[cmd.index("--dir") + 1]) / "field.pt").write_bytes(weights)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mocker.patch.object(fetch.subprocess, "run", side_effect=fake_gh)
    import hashlib

    model = {
        "name": "field",
        "asset": "field.pt",
        "dest": "production/field/weights/best.pt",
        "sha256": hashlib.sha256(weights).hexdigest(),
        "size_bytes": len(weights),
        "recipe": RECIPE,
    }
    fetch.download(model, "o/r", "t")
    folder = tmp_path / "production" / "field"
    assert (folder / "weights" / "best.pt").read_bytes() == weights
    assert json.loads((folder / "recipe.json").read_text()) == RECIPE


def test_fetch_writes_no_recipe_for_an_entry_without_one(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    fetch = load("fetch_models")
    mocker.patch.object(fetch, "ROOT", str(tmp_path))

    def fake_gh(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        (Path(cmd[cmd.index("--dir") + 1]) / "g.pt").write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mocker.patch.object(fetch.subprocess, "run", side_effect=fake_gh)
    import hashlib

    model = {
        "name": "g",
        "asset": "g.pt",
        "dest": "production/g/weights/best.pt",
        "sha256": hashlib.sha256(b"x").hexdigest(),
        "size_bytes": 1,
    }
    fetch.download(model, "o/r", "t")
    assert not (tmp_path / "production" / "g" / "recipe.json").exists()
