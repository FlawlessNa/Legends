"""
Download the YOLO weights this checkout expects.

Weights are not stored in git -- they are attached to a GitHub Release and
pinned by `models.manifest.json`. This script downloads them, verifies each
against its recorded SHA-256, and places it where the bot looks for it.

Usage
-----
    python scripts/fetch_models.py            # download whatever is missing or stale
    python scripts/fetch_models.py --check    # report status, download nothing
    python scripts/fetch_models.py --force    # re-download even if already valid
    python scripts/fetch_models.py global     # only the named model(s)

Requires the `gh` CLI, authenticated against a private repo you have access to:
    winget install GitHub.cli && gh auth login
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


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_current(model: dict) -> bool:
    """True when the model is already on disk with the exact pinned contents."""
    dest = os.path.join(ROOT, model["dest"])
    if not os.path.exists(dest):
        return False
    if os.path.getsize(dest) != model["size_bytes"]:
        return False
    return sha256_of(dest) == model["sha256"]


def require_gh() -> None:
    if shutil.which("gh") is None:
        sys.exit(
            "The `gh` CLI is required to download from a private repo's releases.\n"
            "  Install:   winget install GitHub.cli\n"
            "  Authorise: gh auth login\n"
            "Then re-run this script."
        )


def download(model: dict, repo: str, tag: str) -> None:
    dest = os.path.join(ROOT, model["dest"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                repo,
                "--pattern",
                model["asset"],
                "--dir",
                tmp,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            sys.exit(
                f"Failed to download {model['asset']} from {repo}@{tag}:\n"
                f"{result.stderr.strip()}\n"
                "Check that you have access to the repo and that the release exists."
            )

        downloaded = os.path.join(tmp, model["asset"])
        actual = sha256_of(downloaded)
        if actual != model["sha256"]:
            sys.exit(
                f"Checksum mismatch for {model['asset']}.\n"
                f"  expected {model['sha256']}\n"
                f"  got      {actual}\n"
                "The release asset does not match models.manifest.json. Do not use "
                "this file -- ask whoever published the release to re-check it."
            )
        # Move into place only once verified, so a failure never leaves a
        # half-written model where the bot would happily load it.
        shutil.move(downloaded, dest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "names",
        nargs="*",
        help="Model names to fetch. Defaults to every model in the manifest.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report which models are present and current; download nothing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even models that are already present and valid.",
    )
    args = parser.parse_args()

    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)

    repo, tag = manifest["repo"], manifest["release_tag"]
    wanted = manifest["models"]
    if args.names:
        known = {m["name"] for m in wanted}
        unknown = set(args.names) - known
        if unknown:
            sys.exit(
                f"Unknown model(s): {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(known))}"
            )
        wanted = [m for m in wanted if m["name"] in args.names]

    if args.check:
        missing = 0
        for model in wanted:
            ok = is_current(model)
            missing += not ok
            print(
                f"  {'OK     ' if ok else 'MISSING'} {model['name']:<20} {model['dest']}"
            )
        print(
            f"\n{len(wanted) - missing}/{len(wanted)} models present and matching "
            f"{os.path.basename(MANIFEST)}."
        )
        return 1 if missing else 0

    require_gh()
    for model in wanted:
        if not args.force and is_current(model):
            print(f"  up to date  {model['name']}")
            continue
        size_mb = model["size_bytes"] / 1024 / 1024
        print(f"  downloading {model['name']} ({size_mb:.1f} MB)...")
        download(model, repo, tag)
        print(f"  installed   {model['dest']}")

    print(f"\nAll models ready under {os.path.join('data', 'models', 'production')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
