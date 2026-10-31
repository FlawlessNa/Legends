"""`python -m ml_training`: commands for the detection-model tooling."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ml_training")
    commands = parser.add_subparsers(dest="command", required=True)

    scoring = commands.add_parser(
        "score",
        help="Print a model's precision, recall and mAP50 on a recording.",
    )
    scoring.add_argument("model", help="a model folder or a weights path")
    scoring.add_argument(
        "recording",
        help="a recording folder (images/, labels/, classes.txt), or a model "
        "name to use its newest recording",
    )

    synth = commands.add_parser(
        "synth",
        help="Generate scenes of a map, train a model on them, and write it.",
    )
    synth.add_argument("map", nargs="?", help="its name, or its ID")
    synth.add_argument("--count", type=int, help="scenes to generate (default 3000)")
    synth.add_argument("--seed", type=int, help="default: drawn, and printed")
    synth.add_argument("--build", help="the extraction's build (default: the latest)")
    synth.add_argument("--name", help="the model's folder name (default: the map ID)")
    synth.add_argument(
        "--recipe", type=Path, help="a recipe.json to run again; flags override it"
    )
    synth.add_argument(
        "--keep-dataset", action="store_true", help="don't delete the dataset"
    )
    synth.add_argument("--root", type=Path, help="the game_data store")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "score":
        from .model_manager.recording import score

        metrics = score(args.model, args.recording)
        print(f"precision: {metrics['precision']:.3f}")
        print(f"recall:    {metrics['recall']:.3f}")
        print(f"mAP50:     {metrics['mAP50']:.3f}")
    elif args.command == "synth":
        return _synth(args)
    return 0


def _synth(args: argparse.Namespace) -> int:
    # Here, not at the top: it loads `cv2` and `ultralytics`.
    from game_data.catalogue import CatalogueError
    from game_data.config import STORE
    from game_data.render import RenderError
    from game_data.scenes import SceneError

    from .synthetic import SynthError, synth

    try:
        synth(
            args.map,
            count=args.count,
            seed=args.seed,
            build=args.build,
            name=args.name,
            recipe=args.recipe,
            keep_dataset=args.keep_dataset,
            root=args.root or STORE,
        )
    except (CatalogueError, RenderError, SceneError, SynthError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except LookupError as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
