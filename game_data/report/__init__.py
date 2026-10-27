"""
The patch report: what changed between two extractions, as one HTML page.

- `write_report(store, old, new)`: writes `reports/<old>__<new>.html`, and is
  the report hook `extract` calls (`report`).
- `diff_raw`: which images were added, removed or changed, and the nodes that
  differ inside a changed one (`diff`).
- `summarize`: the maps, mobs and skills that were added, removed or changed,
  from the two catalogues (`summary`).
- `render`: the self-contained page (`page`).

It reads two extractions and never the client.
"""

from .diff import ImageChange, NodeChange, RawDiff, diff_raw, diff_trees
from .page import render
from .report import report_path, write_report
from .summary import (
    FieldChange,
    GeometryChange,
    LevelChange,
    MapChange,
    MobChange,
    SkillChange,
    Summary,
    summarize,
)

__all__ = [
    "FieldChange",
    "GeometryChange",
    "ImageChange",
    "LevelChange",
    "MapChange",
    "MobChange",
    "NodeChange",
    "RawDiff",
    "SkillChange",
    "Summary",
    "diff_raw",
    "diff_trees",
    "render",
    "report_path",
    "summarize",
    "write_report",
]
