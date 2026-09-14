"""
Launcher for training a new monster detection class.

USAGE
-----
Activate your venv, then from the repo root:

    python ml_training/run.py

SETTINGS
--------
Edit the CONFIG block below to change class name, sample counts, and model size.

For training hyperparameters (epochs, batch size, augmentation, etc.)
edit: ml_training/config/settings.yaml

HOW IT WORKS
------------
Phase 1 — Initial bootstrap  (~10 images, annotated manually)
  Capture a handful of screenshots, open the annotation GUI, draw boxes,
  then train a quick mini-model.  The mini-model doesn't need to be great —
  it just needs to find the target often enough to speed up Phase 2.

Phase 2 — Active learning    (~50-100 images, model-assisted)
  Capture a larger batch. The mini-model runs on all of them and pre-fills
  boxes in the GUI. You only correct mistakes instead of drawing from scratch.
  This is ~10x faster than fully manual annotation.

Phase 3 — Final training
  Combines all annotated data and trains the production model.
  The result is exported to data/models/production/{CLASS_NAME}/weights/best.pt
  which is directly loadable by the bot.
"""

import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil

from botting.utilities.client_handler import get_open_clients
from ml_training.gui import AnnotatorAborted
from ml_training.workflows import BootstrapNewClass, train_global_production_model

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — edit this section for each new class you train
# ─────────────────────────────────────────────────────────────────────────────

# Session name — used for folder and model naming only.
# For a single class, set this to the class name.
# For multi-class, use a descriptive map/group name (e.g. "GS2Map").
SESSION_NAME = "Bubbling"

# Detection classes to annotate and train.
# Always include "Character" — it is always on-screen and must be annotated
# so the global model keeps detecting it correctly alongside new monsters.
# Single class:   CLASSES = ["Character", "PacPinky"]
# Multi-class:    CLASSES = ["Character", "Slimy", "SelkieJr", "PlatoonChronos"]
CLASSES = ["Bubbling", "Character"]

# Number of screenshots to capture for each phase.
# Phase 1: small set, you annotate everything manually from scratch.
# Phase 2: large set, the mini-model pre-fills boxes for you to verify.
INITIAL_SAMPLES = 5
EXTENDED_SAMPLES = 50

# YOLO model size: 'n' (nano), 's' (small), 'm' (medium), 'l' (large), 'x'
# Start with 'n' — it trains fast and is usually sufficient for game sprites.
MODEL_SIZE = "n"

# ── Skip flags — set True for phases you've already completed ─────────────────
#
# SKIP_PHASE_1: skip capture + annotation + mini-train entirely.
#   Requires: mini model already in registry (data/models/registry/).
#   Use when: you ran Phase 1 in a previous session.
SKIP_PHASE_1 = True

# SKIP_EXTENDED_CAPTURE: skip capturing the ~EXTENDED_SAMPLES extended images.
#   Requires: images already exist in data/captures/{SESSION_NAME}_extended/.
#   Use when: extended images were already captured.
SKIP_EXTENDED_CAPTURE = True

# SKIP_PREANNOTATION: don't re-run the mini model over the extended images —
#   keep the label files already in data/captures/{SESSION_NAME}_extended_labels/.
#   Requires: label files already exist there (verified and/or pre-annotated).
#   Use when: resuming a crashed verify session, so labels you already verified
#   are NOT overwritten by fresh predictions. The verify GUI reopens on them;
#   press Enter to skip through images you already verified.
SKIP_PREANNOTATION = True

# REANNOTATE: re-open the annotator on all existing images so you can add boxes
#   for new classes without re-capturing anything.
#   Skips: all captures, mini-model training, live viewer, pre-annotation.
#   Runs:  annotate GUI on initial images, annotate GUI on extended images, final train.
#   Use when: you forgot a class (e.g. "Character") and need to add it to existing data.
REANNOTATE = False

# When REANNOTATE=True, pre-fill boxes for these classes on ALL images using
# the model at PREANNOTATE_MODEL_PATH before the annotator opens.
# Set to [] to skip pre-annotation and draw everything manually.
REANNOTATE_PREANNOTATE_CLASSES: list[str] = ["Character"]
PREANNOTATE_MODEL_PATH = "data/model_runs/models/production/global/weights/best.pt"

# RETRAIN_EVERY: retrain the model after every N verified images in the verify GUI.
#   0 = disabled (use original mini model for all pre-annotations).
#   Recommended: 10-15. Each retrain improves pre-annotations for remaining images.
RETRAIN_EVERY = 10

# ── Post-training options ──────────────────────────────────────────────────────

# CLEANUP: remove intermediate derived files after training.
#   Your captures + annotations in data/captures/ are NEVER removed.
#   Keeps: captures/, datasets/{session}_final/, models/registry/,
#          models/production/, models/runs/{session}_final/ (metrics/curves)
#   Removes: datasets/{session}_initial, _combined, _iter* (copies of captures, regenerable)
#            models/runs/{session}_mini, _iter*             (temporary training artifacts)
CLEANUP = True

# GLOBAL_RETRAIN: after the per-session model, train one global model with all
#   classes by merging this session's final dataset with the paths listed below.
#   The global model is what you set as "All" in the bot's models_path config.
GLOBAL_RETRAIN = True

# RETRAIN_GLOBAL_ONLY: skip the entire bootstrap workflow and only retrain the
#   global "All" model from the datasets listed in GLOBAL_DATASET_PATHS.
#   No game window needed. SESSION_NAME / CLASSES / skip flags are all ignored.
RETRAIN_GLOBAL_ONLY = True

# Paths to include in the global model (in addition to this session's data,
# unless RETRAIN_GLOBAL_ONLY=True in which case only these paths are used).
# Each path must be a YOLO-format dataset directory containing a data.yaml file.
#
# After training a new monster class, append its {SESSION_NAME}_final dataset
# here. Each dataset keeps its own local class IDs; the merge remaps them into
# a unified class list using each dataset's data.yaml (and aborts if labels and
# data.yaml disagree). The bot looks up detections by class NAME from the
# model, so IDs shifting between retrains is harmless — never edit a
# pipeline-generated data.yaml by hand.
GLOBAL_DATASET_PATHS: list[str] = [
    "data/datasets/GS2MobsAndChar",
    "data/datasets/ChronosAndMp3WithCharacter",
    "data/datasets/PacPinky_final",  # session data — the YOLO-formatted dataset, not raw captures
    "data/datasets/Bubbling_final",
]

# ─────────────────────────────────────────────────────────────────────────────


def get_game_handle() -> int:
    """Detect open game clients and return the handle to capture from."""
    clients = get_open_clients()

    if not clients:
        print("ERROR: No game window found. Make sure the client is open.")
        sys.exit(1)

    if len(clients) == 1:
        import win32gui

        title = win32gui.GetWindowText(clients[0])
        print(f"Found game window: '{title}'  (handle {clients[0]})")
        return clients[0]

    # Multiple clients open — let the user pick
    import win32gui

    print("Multiple game windows found:")
    for i, hwnd in enumerate(clients):
        print(f"  [{i}] {win32gui.GetWindowText(hwnd)}  (handle {hwnd})")
    while True:
        choice = input("Enter the number of the window to capture: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(clients):
            return clients[int(choice)]
        print("Invalid choice, try again.")


def _cleanup(wf: BootstrapNewClass) -> None:
    """Delete all captures and datasets produced by this run."""
    dirs_to_remove = [
        wf.raw_images_dir,
        wf.annotations_dir,
        wf.base_path / "captures" / f"{wf.class_name}_extended",
        wf.base_path / "captures" / f"{wf.class_name}_extended_labels",
        wf.base_path / "datasets" / wf.initial_dataset_name,
        wf.base_path / "datasets" / wf.final_dataset_name,
        wf.base_path / "datasets" / f"{wf.class_name}_combined",
    ]
    removed = []
    for d in dirs_to_remove:
        if d.exists():
            shutil.rmtree(d)
            removed.append(str(d))
    if removed:
        print("\nCleaned up:")
        for r in removed:
            print(f"  deleted  {r}")
    else:
        print("\nNothing to clean up.")


def main():
    if REANNOTATE and RETRAIN_GLOBAL_ONLY:
        print("ERROR: REANNOTATE and RETRAIN_GLOBAL_ONLY cannot both be True.")
        print("  Set RETRAIN_GLOBAL_ONLY = False to run the reannotate workflow.")
        sys.exit(1)

    if RETRAIN_GLOBAL_ONLY:
        if not GLOBAL_DATASET_PATHS:
            print("ERROR: RETRAIN_GLOBAL_ONLY=True but GLOBAL_DATASET_PATHS is empty.")
            sys.exit(1)
        print(f"\n{'=' * 60}")
        print("  Global model retrain (RETRAIN_GLOBAL_ONLY)")
        print(f"{'=' * 60}")
        for p in GLOBAL_DATASET_PATHS:
            print(f"  + {p}")
        print(f"{'=' * 60}\n")
        train_global_production_model(
            dataset_paths=GLOBAL_DATASET_PATHS,
            name="global",
            model_size=MODEL_SIZE,
        )
        return

    print(f"\n{'=' * 60}")
    print(f"  ML Training — Session: {SESSION_NAME}")
    print(f"{'=' * 60}")
    print(f"  Classes      : {CLASSES}")
    print(f"  Model size   : {MODEL_SIZE}")
    print(f"  Initial imgs : {INITIAL_SAMPLES}")
    print(f"  Extended imgs: {EXTENDED_SAMPLES}")
    print(f"{'=' * 60}\n")

    handle = get_game_handle()

    wf = BootstrapNewClass(
        session_name=SESSION_NAME,
        classes=CLASSES,
        window_handle=handle,
    )

    try:
        _run(wf)
    except AnnotatorAborted:
        print("\n--- Session aborted by user ---")
        _cleanup(wf)
        sys.exit(0)


def _run(wf: BootstrapNewClass) -> None:

    # ── Re-annotate mode: add missing classes to existing images ───────────────
    if REANNOTATE:
        wf.extended_images_dir = wf.base_path / "captures" / f"{SESSION_NAME}_extended"
        wf.extended_annotations_dir = (
            wf.base_path / "captures" / f"{SESSION_NAME}_extended_labels"
        )

        # Pre-fill boxes for missing classes using an existing model
        if REANNOTATE_PREANNOTATE_CLASSES:
            model_path = Path(PREANNOTATE_MODEL_PATH)
            if not model_path.exists():
                print(
                    f"WARNING: PREANNOTATE_MODEL_PATH not found: {PREANNOTATE_MODEL_PATH}"
                )
                print("Skipping pre-annotation — you will draw all boxes manually.")
            else:
                print(f"\nPre-annotating with {PREANNOTATE_MODEL_PATH}…")
                for images_dir, labels_dir in [
                    (wf.raw_images_dir, wf.annotations_dir),
                    (wf.extended_images_dir, wf.extended_annotations_dir),
                ]:
                    if images_dir.exists():
                        wf.preannotate_with_model(
                            model_path=str(model_path),
                            images_dir=images_dir,
                            labels_dir=labels_dir,
                            target_classes=REANNOTATE_PREANNOTATE_CLASSES,
                        )

        print(
            "\nRe-annotating initial images — verify pre-filled boxes, add any missing."
        )
        wf.annotate_initial_samples()

        wf.reannotate_extended_samples()

        wf.train_final_model(model_size=MODEL_SIZE)
        wf.evaluate()
        session_prod_path = wf.export_to_production()

        if GLOBAL_RETRAIN:
            final_dataset = str(wf.base_path / "datasets" / wf.final_dataset_name)
            global_prod_path = train_global_production_model(
                dataset_paths=[final_dataset] + GLOBAL_DATASET_PATHS,
                name="global",
                model_size=MODEL_SIZE,
            )
        if CLEANUP:
            wf.cleanup_intermediate()
        return

    # ── Phase 1: initial bootstrap ──────────────────────────────────────────
    if not SKIP_PHASE_1:
        input("Position the game window, then press ENTER to start capture…")
        wf.capture_initial_samples(count=INITIAL_SAMPLES)

        print("\nOpening annotation GUI — draw boxes around every instance.")
        print(
            "Controls:  A/D = prev/next   Ctrl+Click = remove box   Del = delete last box   Ctrl+S = save\n"
        )
        wf.annotate_initial_samples()

        wf.train_mini_model(model_size=MODEL_SIZE)
    else:
        print("[skip] Phase 1 — restoring mini model from registry…")
        latest = wf.registry.get_latest_model(f"{SESSION_NAME}_mini")
        if latest is None:
            # Fall back to the raw training output if not registered
            fallback = (
                wf.base_path
                / "models"
                / "runs"
                / f"{SESSION_NAME}_mini"
                / "weights"
                / "best.pt"
            )
            alt = (
                Path("data/models/runs")
                / f"{SESSION_NAME}_mini"
                / "weights"
                / "best.pt"
            )
            candidate = fallback if fallback.exists() else alt if alt.exists() else None
            if candidate is None:
                print(
                    "ERROR: No mini model found. Set SKIP_PHASE_1 = False to train one."
                )
                sys.exit(1)
            wf.mini_model_path = str(candidate)
        else:
            wf.mini_model_path = latest["model_path"]
        print(f"       Using: {wf.mini_model_path}")

    # ── Live inference check ────────────────────────────────────────────────
    # Validate the mini model and choose inference thresholds for pre-annotation.
    conf, iou = wf.verify_mini_model()

    # ── Phase 2: active learning ─────────────────────────────────────────────
    if not SKIP_EXTENDED_CAPTURE:
        input("\nPosition the game window, then press ENTER to start extended capture…")
        wf.capture_extended_samples(count=EXTENDED_SAMPLES)
    else:
        print("[skip] Extended capture — using existing images…")
        wf.extended_images_dir = wf.base_path / "captures" / f"{SESSION_NAME}_extended"
        if not wf.extended_images_dir.exists():
            print(f"ERROR: Expected {wf.extended_images_dir} but it does not exist.")
            sys.exit(1)

    wf.predict_and_verify(
        conf=conf,
        iou=iou,
        retrain_every=RETRAIN_EVERY,
        model_size=MODEL_SIZE,
        skip_preannotation=SKIP_PREANNOTATION,
    )

    # ── Phase 3: final training ──────────────────────────────────────────────
    wf.train_final_model(model_size=MODEL_SIZE)
    wf.evaluate()
    session_prod_path = wf.export_to_production()

    # ── Global retrain (optional) ────────────────────────────────────────────
    global_prod_path = None
    if GLOBAL_RETRAIN:
        final_dataset = str(wf.base_path / "datasets" / wf.final_dataset_name)
        all_sources = [final_dataset] + GLOBAL_DATASET_PATHS
        global_prod_path = train_global_production_model(
            dataset_paths=all_sources,
            name="global",
            model_size=MODEL_SIZE,
        )

    # ── Cleanup ──────────────────────────────────────────────────────────────
    if CLEANUP:
        wf.cleanup_intermediate()

    print(f"\n{'=' * 60}")
    print("  Done!")
    if global_prod_path:
        print(f'  Global model → "models_path": {{"All": "{global_prod_path}"}}')
    else:
        print(f"  Session model: {session_prod_path}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
