"""
Publish the current production weights as a GitHub Release and re-pin the manifest.

Run this after `promote_to_production()` puts a new model under
`data/models/production/`. It uploads each model's `weights/best.pt` as a
release asset, then rewrites `models.manifest.json` with the new checksums so
that `scripts/fetch_models.py` hands everyone else the same bytes.

Usage
-----
    python scripts/publish_models.py --dry-run          # show what would happen
    python scripts/publish_models.py                    # publish to the manifest's tag
    python scripts/publish_models.py --tag models-v2    # publish under a new tag

Commit the resulting `models.manifest.json` -- that commit is what tells
everyone else there are new weights to fetch.

Requires the `gh` CLI, authenticated with write access to the repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "models.manifest.json")
PRODUCTION = os.path.join(ROOT, "data", "models", "production")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def discover() -> list[dict]:
    """Every production model on disk, as manifest entries."""
    if not os.path.isdir(PRODUCTION):
        sys.exit(f"No production models found at {PRODUCTION}.")

    found = []
    for name in sorted(os.listdir(PRODUCTION)):
        weights = os.path.join(PRODUCTION, name, "weights", "best.pt")
        if not os.path.exists(weights):
            continue
        found.append(
            {
                "name": name,
                "asset": f"{name}.pt",
                "dest": f"data/models/production/{name}/weights/best.pt",
                "sha256": sha256_of(weights),
                "size_bytes": os.path.getsize(weights),
                "_source": weights,
            }
        )
    if not found:
        sys.exit(f"No */weights/best.pt under {PRODUCTION}.")
    return found


def carry_over_docs(models: list[dict], previous: list[dict]) -> None:
    """Keep the hand-written description/classes from the existing manifest."""
    by_name = {m["name"]: m for m in previous}
    for model in models:
        prior = by_name.get(model["name"], {})
        for field in ("description", "classes"):
            if field in prior:
                model[field] = prior[field]


def ensure_release(repo: str, tag: str, dry_run: bool) -> None:
    exists = run(["gh", "release", "view", tag, "--repo", repo]).returncode == 0
    if exists:
        print(f"  release {tag} already exists -- assets will be replaced")
        return
    if dry_run:
        print(f"  would create release {tag}")
        return
    print(f"  creating release {tag}")
    result = run(
        [
            "gh", "release", "create", tag,
            "--repo", repo,
            "--title", f"Detection models ({tag})",
            "--notes",
            (
                "YOLO detection weights for this repo. Do not download by hand"
                " -- run `python scripts/fetch_models.py`, which verifies each"
                " file against `models.manifest.json`."
            ),
        ]
    )
    if result.returncode != 0:
        sys.exit(f"Failed to create release {tag}:\n{result.stderr.strip()}")


def upload(model: dict, repo: str, tag: str, dry_run: bool) -> None:
    size_mb = model["size_bytes"] / 1024 / 1024
    if dry_run:
        print(f"  would upload {model['asset']} ({size_mb:.1f} MB)")
        return

    # gh uploads under the file's own name, so stage it under the asset name.
    with tempfile.TemporaryDirectory() as tmp:
        staged = os.path.join(tmp, model["asset"])
        shutil.copyfile(model["_source"], staged)
        print(f"  uploading {model['asset']} ({size_mb:.1f} MB)...")
        result = run(
            ["gh", "release", "upload", tag, staged, "--repo", repo, "--clobber"]
        )
        if result.returncode != 0:
            sys.exit(f"Failed to upload {model['asset']}:\n{result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--tag", help="Release tag. Defaults to the manifest's.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and the resulting manifest; upload nothing.",
    )
    args = parser.parse_args()

    if shutil.which("gh") is None:
        sys.exit("The `gh` CLI is required. Install it and run `gh auth login`.")

    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)

    repo = manifest["repo"]
    tag = args.tag or manifest["release_tag"]
    models = discover()
    carry_over_docs(models, manifest.get("models", []))

    print(f"Publishing {len(models)} model(s) to {repo}@{tag}")
    ensure_release(repo, tag, args.dry_run)
    for model in models:
        upload(model, repo, tag, args.dry_run)

    manifest["release_tag"] = tag
    manifest["models"] = [
        {k: v for k, v in m.items() if not k.startswith("_")} for m in models
    ]
    if args.dry_run:
        print("\nWould write models.manifest.json:\n")
        print(json.dumps(manifest, indent=2))
        return 0

    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print(
        "\nWrote models.manifest.json. Commit it so everyone else knows to run\n"
        "  python scripts/fetch_models.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
