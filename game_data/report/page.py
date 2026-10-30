"""
The HTML page: one self-contained file, with inline CSS and SVG, and the
sprites embedded as `data:` URIs, so it opens with no network and survives
retention deleting the extractions it was made from.

In order: a summary of counts; the maps whose geometry changed, each with the
map drawn before and after (what is gone or different is red on the left, what
is new or different is green on the right); the mobs whose stats changed, as a
table with their sprites before and after; the skills whose levels changed;
what was added and removed; and the raw differences, collapsed.

A real patch can change thousands of images, so the raw section lists the first
`MAX_IMAGES` changed images, and the first `MAX_NODES` differences of each, and
says how many it left out. The counts at the top are always complete.
"""

import base64
import html
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Final

from game_data.catalogue import MapData, Ref
from game_data.extraction import ImageStore, Manifest

from .diff import ImageChange, NodeChange, RawDiff
from .summary import (
    FieldChange,
    MapChange,
    MobChange,
    SkillChange,
    Summary,
    Value,
    anonymous,
    label,
)

MAX_IMAGES: Final = 300
MAX_NODES: Final = 40
MAX_VALUE: Final = 160
# The longest side of a map drawing, in SVG units.
DRAWING: Final = 560

_STYLE: Final = """
:root { color-scheme: light dark; --bg: #fafafa; --fg: #1d1d1f; --muted: #6b6b70;
  --line: #d6d6db; --card: #fff; --gone: #c62828; --new: #1b8a3a; --edit: #b26a00; }
@media (prefers-color-scheme: dark) { :root { --bg: #17171a; --fg: #ececf0;
  --muted: #9a9aa3; --line: #34343a; --card: #202025; --gone: #ff6b6b;
  --new: #5bd47d; --edit: #ffb347; } }
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 70rem;
  padding: 1rem 16px 4rem; font: 15px/1.5 system-ui, sans-serif; }
h1 { margin-bottom: 0; } h2 { margin-top: 2.5rem; border-bottom: 1px solid var(--line); }
h3 { margin-bottom: .25rem; } .muted { color: var(--muted); }
code, .mono { font: 13px ui-monospace, Consolas, monospace; }
table { border-collapse: collapse; margin: .5rem 0; }
td, th { border: 1px solid var(--line); padding: .15rem .6rem; text-align: left;
  vertical-align: top; }
.counts td:first-child { font-weight: 600; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: .25rem 1rem 1rem; margin: 1rem 0; }
.pair { display: flex; flex-wrap: wrap; gap: 1rem; }
.pair figure { margin: 0; } figcaption { color: var(--muted); font-size: 13px; }
svg { background: var(--bg); border: 1px solid var(--line); max-width: 100%; height: auto; }
img.sprite { image-rendering: pixelated; max-width: 220px; max-height: 220px;
  background: var(--bg); border: 1px solid var(--line); }
.added { color: var(--new); } .removed { color: var(--gone); }
.changed { color: var(--edit); }
details { margin: .5rem 0; } summary { cursor: pointer; }
"""


def render(
    old: Manifest,
    new: Manifest,
    raw: RawDiff,
    summary: Summary,
    images: ImageStore,
) -> str:
    """
    The patch report from `old` to `new`.

    :param images: The image store the sprites are read from, and embedded.
    """
    title = f"Patch report: {old.build} to {new.build}"
    body = [
        f"<h1>{_e(title)}</h1>",
        f'<p class="muted">{_when(old)} &rarr; {_when(new)}</p>',
        _counts(raw, summary),
        _maps(summary),
        _mobs(summary, images),
        _skills(summary),
        _raw(raw),
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head><body>"
        + "".join(body)
        + "</body></html>"
    )


def _e(text: object) -> str:
    return html.escape(str(text))


def _when(manifest: Manifest) -> str:
    stamp: datetime = manifest.extracted_at
    return (
        f"build <code>{_e(manifest.build)}</code>, extracted {stamp:%Y-%m-%d %H:%M} UTC"
    )


def _value(value: Value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > MAX_VALUE:
        text = text[: MAX_VALUE - 1] + "…"
    return f'<span class="mono">{_e(text)}</span>'


# --- the summary of counts ---------------------------------------------------


def _counts(raw: RawDiff, summary: Summary) -> str:
    rows = [
        (
            "Maps",
            len(summary.maps_added),
            len(summary.maps_removed),
            len(summary.maps_changed),
        ),
        (
            "Mobs",
            len(summary.mobs_added),
            len(summary.mobs_removed),
            len(summary.mobs_changed),
        ),
        (
            "Skills",
            len(summary.skills_added),
            len(summary.skills_removed),
            len(summary.skills_changed),
        ),
        ("Images (raw)", len(raw.added), len(raw.removed), len(raw.changed)),
    ]
    cells = "".join(
        f"<tr><td>{kind}</td><td class='added'>{added}</td>"
        f"<td class='removed'>{removed}</td><td class='changed'>{changed}</td></tr>"
        for kind, added, removed, changed in rows
    )
    return (
        '<h2>Summary</h2><table class="counts"><tr><th></th><th>added</th>'
        f"<th>removed</th><th>changed</th></tr>{cells}</table>"
    )


# --- maps --------------------------------------------------------------------


def _maps(summary: Summary) -> str:
    parts = ["<h2>Maps</h2>"]
    if not (summary.maps_changed or summary.maps_added or summary.maps_removed):
        return parts[0] + '<p class="muted">No map changed.</p>'
    parts.append(_refs("Added", "added", summary.maps_added))
    parts.append(_refs("Removed", "removed", summary.maps_removed))
    for change in summary.maps_changed:
        parts.append(_map(change))
    return "".join(parts)


def _refs(heading: str, css: str, refs: Iterable[Ref]) -> str:
    listed = "".join(f"<li>{_e(label(ref.id, ref.name))}</li>" for ref in refs)
    if not listed:
        return ""
    return f'<h3 class="{css}">{heading}</h3><ul>{listed}</ul>'


def _map(change: MapChange) -> str:
    rows = "".join(
        f"<tr><td class='{c.kind}'>{c.kind}</td><td>{_e(c.subject)}</td>"
        f"<td>{_e(c.old or '')}</td><td>{_e(c.new or '')}</td></tr>"
        for c in change.changes
    )
    return (
        f'<div class="card"><h3>{_e(label(change.id, change.name))}</h3>'
        f"<table><tr><th></th><th>what</th><th>before</th><th>after</th></tr>"
        f"{rows}</table>"
        '<div class="pair">'
        f"<figure>{_drawing(change.before, change.after, gone=True)}"
        "<figcaption>before</figcaption></figure>"
        f"<figure>{_drawing(change.after, change.before, gone=False)}"
        "<figcaption>after</figcaption></figure></div></div>"
    )


def _drawing(shown: MapData, other: MapData, *, gone: bool) -> str:
    """
    `shown` as SVG in virtual coordinates. What `other` doesn't have the same is
    marked: red if `gone`, else green.
    """
    xs = [shown.vr.left, shown.vr.right, other.vr.left, other.vr.right]
    ys = [shown.vr.top, shown.vr.bottom, other.vr.top, other.vr.bottom]
    for each in (shown, other):
        for f in each.footholds:
            xs += [f.x1, f.x2]
            ys += [f.y1, f.y2]
        for r in each.ropes:
            xs.append(r.x)
            ys += [r.y1, r.y2]
        for p in each.portals:
            xs.append(p.x)
            ys.append(p.y)
        for s in each.spawns:
            xs.append(s.x)
            ys.append(s.cy)
    left, top = min(xs), min(ys)
    width, height = max(max(xs) - left, 1), max(max(ys) - top, 1)
    margin = max(width, height) // 40 + 5
    scale = DRAWING / (max(width, height) + 2 * margin)
    mark = "var(--gone)" if gone else "var(--new)"
    drawn: list[str] = []

    def colour(same: bool) -> str:
        return "currentColor" if same else mark

    vr = shown.vr
    drawn.append(
        f'<rect x="{vr.left}" y="{vr.top}" width="{vr.right - vr.left}" '
        f'height="{vr.bottom - vr.top}" fill="none" stroke="var(--muted)" '
        'stroke-dasharray="6 4" vector-effect="non-scaling-stroke"/>'
    )
    for r in shown.ropes:
        drawn.append(
            f'<line x1="{r.x}" y1="{r.y1}" x2="{r.x}" y2="{r.y2}" '
            f'stroke="{colour(anonymous(r) in {anonymous(x) for x in other.ropes})}" stroke-width="1.5" '
            'vector-effect="non-scaling-stroke" opacity=".7"/>'
        )
    for f in shown.footholds:
        drawn.append(
            f'<line x1="{f.x1}" y1="{f.y1}" x2="{f.x2}" y2="{f.y2}" '
            f'stroke="{colour(anonymous(f) in {anonymous(x) for x in other.footholds})}" stroke-width="2.5" '
            'vector-effect="non-scaling-stroke"/>'
        )
    radius = 4 / scale
    for p in shown.portals:
        drawn.append(
            f'<circle cx="{p.x}" cy="{p.y}" r="{radius:.1f}" fill="none" '
            f'stroke="{colour(p in other.portals)}" stroke-width="2" '
            'vector-effect="non-scaling-stroke"/>'
        )
    for s in shown.spawns:
        drawn.append(
            f'<rect x="{s.x - radius / 2:.1f}" y="{s.cy - radius / 2:.1f}" '
            f'width="{radius:.1f}" height="{radius:.1f}" '
            f'fill="{colour(s in other.spawns)}"/>'
        )
    box = f"{left - margin} {top - margin} {width + 2 * margin} {height + 2 * margin}"
    return (
        f'<svg viewBox="{box}" width="{DRAWING}" role="img" '
        f'aria-label="{_e(label(shown.id, shown.name))}">{"".join(drawn)}</svg>'
    )


# --- mobs --------------------------------------------------------------------


def _mobs(summary: Summary, images: ImageStore) -> str:
    if not (summary.mobs_changed or summary.mobs_added or summary.mobs_removed):
        return '<h2>Mobs</h2><p class="muted">No mob changed.</p>'
    parts = [
        "<h2>Mobs</h2>",
        _refs("Added", "added", summary.mobs_added),
        _refs("Removed", "removed", summary.mobs_removed),
    ]
    for change in summary.mobs_changed:
        parts.append(_mob(change, images))
    return "".join(parts)


def _mob(change: MobChange, images: ImageStore) -> str:
    return (
        f'<div class="card"><h3>{_e(label(change.id, change.name))}</h3>'
        f"{_fields(change.stats, 'stat')}"
        '<div class="pair">'
        f"<figure>{_sprite(change.before, images)}<figcaption>before</figcaption></figure>"
        f"<figure>{_sprite(change.after, images)}<figcaption>after</figcaption></figure>"
        "</div></div>"
    )


def _sprite(name: str | None, images: ImageStore) -> str:
    """The image embedded; text when there is none, or the store has lost it."""
    if name is None:
        return '<span class="muted">no sprite</span>'
    file = images.path(name)
    try:
        data = base64.b64encode(file.read_bytes()).decode("ascii")
    except OSError:
        return '<span class="muted">sprite no longer in the image store</span>'
    return f'<img class="sprite" alt="sprite" src="data:image/png;base64,{data}">'


def _fields(changes: Iterable[FieldChange], heading: str) -> str:
    rows = "".join(
        f"<tr><td>{_e(c.field)}</td><td>{_value(c.old)}</td><td>{_value(c.new)}</td></tr>"
        for c in changes
    )
    return (
        f"<table><tr><th>{heading}</th><th>before</th><th>after</th></tr>{rows}</table>"
    )


# --- skills ------------------------------------------------------------------


def _skills(summary: Summary) -> str:
    if not (summary.skills_changed or summary.skills_added or summary.skills_removed):
        return '<h2>Skills</h2><p class="muted">No skill changed.</p>'
    parts = [
        "<h2>Skills</h2>",
        _refs("Added", "added", summary.skills_added),
        _refs("Removed", "removed", summary.skills_removed),
    ]
    for change in summary.skills_changed:
        parts.append(_skill(change))
    return "".join(parts)


def _skill(change: SkillChange) -> str:
    notes = ""
    if change.levels_added:
        notes += (
            '<p class="added">levels added: '
            f"{_e(', '.join(map(str, change.levels_added)))}</p>"
        )
    if change.levels_removed:
        notes += (
            '<p class="removed">levels removed: '
            f"{_e(', '.join(map(str, change.levels_removed)))}</p>"
        )
    levels = "".join(
        f"<h4>Level {level.level}</h4>{_fields(level.values, 'value')}"
        for level in change.levels
    )
    return (
        f'<div class="card"><h3>{_e(label(change.id, change.name))}</h3>'
        f"{notes}{levels}</div>"
    )


# --- the raw differences -----------------------------------------------------


def _raw(raw: RawDiff) -> str:
    if not (raw.added or raw.removed or raw.changed):
        return '<h2>Raw differences</h2><p class="muted">No image changed.</p>'
    parts = [
        "<h2>Raw differences</h2>",
        "<details><summary>Show the raw differences</summary>",
        _paths("Added images", "added", raw.added),
        _paths("Removed images", "removed", raw.removed),
        f"<h3>Changed images ({len(raw.changed)})</h3>",
    ]
    for image in raw.changed[:MAX_IMAGES]:
        parts.append(_image(image))
    if len(raw.changed) > MAX_IMAGES:
        parts.append(
            f'<p class="muted">{len(raw.changed) - MAX_IMAGES} more changed images '
            "are not listed.</p>"
        )
    parts.append("</details>")
    return "".join(parts)


def _paths(heading: str, css: str, paths: tuple[str, ...]) -> str:
    if not paths:
        return ""
    shown = "".join(f"<li><code>{_e(path)}</code></li>" for path in paths[:MAX_IMAGES])
    more = (
        f'<li class="muted">{len(paths) - MAX_IMAGES} more not listed</li>'
        if len(paths) > MAX_IMAGES
        else ""
    )
    return f'<h3 class="{css}">{heading} ({len(paths)})</h3><ul>{shown}{more}</ul>'


def _image(image: ImageChange) -> str:
    rows = "".join(_node(node) for node in image.nodes[:MAX_NODES])
    more = (
        f'<p class="muted">{len(image.nodes) - MAX_NODES} more differences '
        "are not listed.</p>"
        if len(image.nodes) > MAX_NODES
        else ""
    )
    table = (
        f"<table><tr><th>node</th><th></th><th>before</th><th>after</th></tr>{rows}</table>"
        if rows
        else '<p class="muted">Its nodes are the same; only their order changed.</p>'
    )
    return (
        f"<details><summary><code>{_e(image.path)}</code> "
        f"({len(image.nodes)} differences)</summary>{table}{more}</details>"
    )


def _node(node: NodeChange) -> str:
    old = "" if node.kind == "added" else _value(node.old)
    new = "" if node.kind == "removed" else _value(node.new)
    return (
        f"<tr><td><code>{_e(node.path or '(image)')}</code></td>"
        f"<td class='{node.kind}'>{node.kind}</td><td>{old}</td><td>{new}</td></tr>"
    )
