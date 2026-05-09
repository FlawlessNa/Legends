"""GUI module for ML Training package."""

try:
    from .annotator import AnnotatorAborted, AnnotatorGUI, run_annotator
    from .live_inference import LiveInferenceViewer, run_live_inference
except ImportError:
    AnnotatorAborted = Exception
    AnnotatorGUI = None
    LiveInferenceViewer = None

    def run_annotator(*args, **kwargs):
        raise ImportError("PyQt6 is required for the annotation GUI. Install it with: pip install PyQt6")

    def run_live_inference(*args, **kwargs):
        raise ImportError("PyQt6 is required for the live inference viewer. Install it with: pip install PyQt6")

__all__ = [
    'AnnotatorAborted', 'AnnotatorGUI', 'run_annotator',
    'LiveInferenceViewer', 'run_live_inference',
]
