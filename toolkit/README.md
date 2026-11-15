# toolkit

Standalone scripts, run by hand. No production code imports them (only `tests/` may,
to test them). Each script's docstring says what it needs and whether it can send
input; the line here is that docstring's first line. `poc_tracking/*.md` describe
the proof-of-concept trackers.

- `toolkit/capture_frames.py`: Save frames of the running client for the frame set.
- `toolkit/extract_model_classes.py`: Copy a YOLO model's class names into the `data.yaml` of its datasets.
- `toolkit/generate_movement_lab_pairs.py`: Regenerate the movement lab's frozen reachability samples.
- `toolkit/graph_build_blocking.py`: Measure how long the decision loop is blocked while a foothold graph builds (#430).
- `toolkit/harvest_glyphs.py`: Cut font-drawn glyphs out of the frame set into `data/glyphs/` (spec R4, #313).
- `toolkit/hsv_filtering.py`: Tune HSV and BGR colour filters live on the client's pixels.
- `toolkit/inspect_dataset.py`: Dataset annotation viewer: browse training images with their YOLO boxes.
- `toolkit/live_detector.py`: Live object detection viewer: run a YOLO model on the client's window.
- `toolkit/movement_attempts.py`: Count how many Attempts each Precision movement took, from a Session's telemetry.
- `toolkit/movement_lab_sweep.py`: Run the movement lab's Invariants over the whole Corpus, and regenerate its goldens.
- `toolkit/movement_playground.py`: Movement playground (#524): send the character to picked targets; it sends input.
- `toolkit/movement_timeline.py`: Visualize a KeyboardInputWrapper as a Gantt-style key-hold timeline.
- `toolkit/poc_tracking/hybrid_tracker.py`: Proof of concept: read the character's position from the minimap and the play area at once.
- `toolkit/poc_tracking/label_frames.py`: Label a folder of frames with the POC trackers' readings, offline.
- `toolkit/poc_tracking/minimap_tracker.py`: Proof of concept: track the character on the map's full minimap canvas, on any map.
- `toolkit/poc_tracking/world_tracker.py`: Proof of concept: read the character's position in virtual (world) coordinates from the play area.
- `toolkit/position_check.py`: Watch and record how the position readers behave, live or over saved frames.
- `toolkit/trial_report.py`: Per-move accuracy report for a Trial: planned against actual, retries, loop timing.
- `toolkit/synthetic_scene.py`: Compose one synthetic client screen of a map and save it with its labels.
- `toolkit/verify_dataset_structure.py`: Check that every dataset under `data/datasets/` has a consistent layout.
