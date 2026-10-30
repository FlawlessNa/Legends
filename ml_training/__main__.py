"""`python -m ml_training`: commands for the detection-model tooling."""

import argparse
from collections.abc import Sequence


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "score":
        from .model_manager.recording import score

        metrics = score(args.model, args.recording)
        print(f"precision: {metrics['precision']:.3f}")
        print(f"recall:    {metrics['recall']:.3f}")
        print(f"mAP50:     {metrics['mAP50']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
