"""
Download the frame set the screen readers are tested on.

The frames are real client screenshots, which can show other players' names, so
they live only in the private repository `legends-frames`, as the assets of one
release per tag. This downloads a tag into `data/frames/<tag>/` (gitignored).

Usage
-----
    python scripts/fetch_frames.py                  # the tag in tests/frames/CURRENT
    python scripts/fetch_frames.py v1               # a given tag
    python scripts/fetch_frames.py --repo me/frames # another repository

The repository's owner defaults to the owner of this checkout's `origin`.
Requires the `gh` CLI: winget install GitHub.cli && gh auth login
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "tests" / "frames" / "CURRENT"
DEST = ROOT / "data" / "frames"
REPO_NAME = "legends-frames"
LOGIN_HINT = "gh is not logged in: run `gh auth login`, then re-run this script."


def default_repo() -> str:
    """`<owner of origin>/legends-frames`."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?\s*$", result.stdout)
    if result.returncode != 0 or not match:
        sys.exit("Can't read the owner from `git remote`: pass --repo OWNER/NAME.")
    return f"{match.group(1)}/{REPO_NAME}"


def current_tag() -> str:
    return CURRENT.read_text(encoding="utf-8").strip()


def logged_in() -> bool:
    return (
        subprocess.run(
            ["gh", "auth", "status"], capture_output=True, check=False
        ).returncode
        == 0
    )


def fetch(tag: str, repo: str, dest: Path = DEST) -> Path:
    """Download every asset of release `tag` of `repo` into `dest/<tag>/`."""
    if shutil.which("gh") is None:
        sys.exit(
            "The `gh` CLI is required: winget install GitHub.cli, then `gh auth login`."
        )
    if not logged_in():
        sys.exit(LOGIN_HINT)
    target = dest / tag
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--dir",
            str(target),
            "--clobber",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(
            f"Failed to download {repo}@{tag}: {result.stderr.strip()}\n"
            "Check that you can access the repository and that the release exists."
        )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "tag", nargs="?", help="Default: the tag in tests/frames/CURRENT."
    )
    parser.add_argument(
        "--repo", help="OWNER/NAME. Default: <origin owner>/legends-frames."
    )
    args = parser.parse_args(argv)

    tag = args.tag or current_tag()
    target = fetch(tag, args.repo or default_repo())
    count = sum(1 for _ in target.glob("*.png"))
    print(f"{count} frames of {tag} in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
