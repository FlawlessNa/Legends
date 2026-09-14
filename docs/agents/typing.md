# Typing

This repo runs a progressive Pyright ratchet: the whole tree must clear a
floor, and one directory is held to a tighter bar than the rest. The goal is
`strict` everywhere, reached a directory at a time rather than in one
big-bang migration — see [ADR 0003](../adr/0003-progressive-typing-ratchet.md)
for why.

## The ratchet

Three mechanisms, all in `[tool.pyright]` in `pyproject.toml`:

1. **The floor** — `typeCheckingMode = "standard"`. The whole governed tree
   (`botting/`, `maple/`, `ml_training/`, `tests/`, `toolkit/`, and the root
   modules) must pass this. `basic` was the fallback if `standard` proved too
   noisy; it didn't — `basic` → `standard` costs under 20 errors repo-wide,
   so there was never a reason to sit at the weaker mode.
2. **The Strict List** — `strict = [...]`. Directories held to Pyright
   `strict`. **Append-only**: an entry is never removed, and no override may
   ever *loosen* a strict-listed directory below what `strict` would already
   catch. Today it holds one entry: `botting/controller/inputs/`.
3. **`reportMissingTypeStubs = "none"`**, set explicitly rather than left at
   its default. Four third-party dependencies — `pytesseract`, `pathfinding`,
   `pytweening`, `fuzzywuzzy` — ship no type stubs and never have any
   upstream; left at the default this rule would fire on every one of their
   call sites, repo-wide, forever. `pywin32` and `keyboard` are the opposite
   case: both have maintained stubs, installed as `types-pywin32` and
   `types-keyboard` in `requirements-dev.txt`.

## Adding a directory to the Strict List

A directory qualifies on two grounds, both required:

- **Stub-clean.** Every third-party import inside it must ship type
  information, natively or via an installed stub package. A directory that
  imports any of the four permanently-unstubbed packages above can never
  qualify while that import stands — this is a hard admission gate, not a
  matter of degree. `botting/controller/inputs/` qualifies only because the
  `pytweening` import sits in `high_level.py`, a *sibling* file directly
  under `botting/controller/`, not inside `inputs/` itself.
- **Load-bearing**, in the judgement of whoever proposes the addition — the
  point of the ratchet is to spend `strict` pressure where a type error is
  most likely to be a real bug, not where it's cheapest to silence.

**Admission does not require the directory to already be clean.**
`botting/controller/inputs/` entered the Strict List carrying 184 strict
errors across its 6 files (0 already clean) — that debt was a known,
accepted cost of admission, not a blocker to it. Pre-existing errors in a
newly strict-listed directory are handled the same way as everywhere else:
fixed as the file is next touched, not bulk-fixed on entry. See
[Not yet specified](https://github.com/FlawlessNa/Legends/issues/76) on the
quality-gates map for what a directory needs beyond stub-cleanliness as the
list grows past its first entry — that cadence isn't settled yet.

## The boy-scout rule

Touching one function in a file governed by the floor — or worse, one inside
the Strict List — surfaces every existing violation *in that file*, not just
the one your change introduced. That is the intended pressure, and the
mechanism the ratchet uses to pay down debt without a bulk migration. What it
must never do is surface violations in files you did not touch — the hooks
are staged-files-only for exactly this reason (see `.pre-commit-config.yaml`).

**Bulk-fixing pre-existing debt is out of scope for this ratchet, by design.**
Both the ~400 repo-wide annotation gaps and the 184 errors inside the pilot
Strict List directory are left as-is. A dedicated bulk-fix effort, if ever
wanted, is its own decision — not something a config-landing change should
do incidentally.

## Off-ratchet directories

The ratchet is per-file, which is exactly right for code that ships, and wrong
for code that does not. These directories report **pyflakes and the correctness
rules only** — no `ANN`, no `T20`, no `BLE001`/`S110`, and no Pyright diagnostics
at all. The two lists live together in `pyproject.toml`
(`[tool.ruff.lint.per-file-ignores]` and `[tool.pyright] ignore`) and must be
kept in step:

| Directory | Why it is off the ratchet |
| --- | --- |
| `ml_training/`, `toolkit/`, `scripts/` | Standalone tools, run by hand. A `print` **is** the interface, and a tool that dies mid-session because it narrowed an exception too far is worse than one that reports and carries on. |
| `maple/model/mechanics/minimap_creation/` | The GUI map editor — same reasoning, plus its `print`s are its UI. |
| `maple/model/mechanics/game_file_extraction/` | The older game-file parser. `map_parser.py` has no importers and is slated for removal (`maple/AGENTS.md`); annotating it is work spent on code on its way out. |
| `maple/decision_makers/inventory_manager.py` | Parked, and raises on import. `maple/AGENTS.md` asks for exactly this: *"When lint and type gates land, exclude this file explicitly rather than editing it into compliance."* |

`ignore` rather than `exclude` for Pyright, deliberately: these files are still
parsed, so code that **is** on the ratchet still gets real types when it imports
them.

Two things this is not. It is not a place to park work you did not feel like
doing — everything pyflakes reports (unused names, undefined names) still applies
here and is still fixed, and so is a stray `breakpoint()`. And it is not
permanent: a directory graduates *onto* the ratchet by being cleaned up and
removed from both lists, the same way `botting/controller/inputs/` graduated onto
the Strict List.

One file carries a single-rule exemption rather than a directory one:
`botting/core/bot_data.py` ignores `ANN401`. `BotData` is a dynamically-typed
attribute store — a managed attribute holds whatever the DecisionMaker that
registered it put there — so `Any` at that module's interface is the accurate
type rather than a lazy one, and narrowing it would only push casts out to every
caller. Every other rule, the rest of `ANN` included, still applies to it.

## Accepted exemptions

The boy-scout rule says *fix, don't suppress*. The exception is a violation whose
root cause is **outside the file you are touching and out of reach** — a
third-party annotation that no value can satisfy, or a base class whose shape is
the real problem. Those may be suppressed with a targeted
`# pyright: ignore[<rule>]` — never a blanket `# type: ignore`, never a file-level
suppression — carrying a comment that names the root cause and why it is out of
reach. A `cast()` is not an alternative: it silences the checker while reading as
if it asserted something true.

Recorded exemptions, so the next person meets them as decisions rather than as
someone's shortcut:

- **`pathfinding.core.diagonal_movement.DiagonalMovement`** is a plain class with
  `int` class attributes that annotates its own parameters as
  `diagonal_movement: DiagonalMovement`. No value of that type exists, so *every*
  caller is a `reportArgumentType` error. `pathfinding` is one of the four
  permanently-unstubbed dependencies above, so there is no upstream fix.
  `MinimapGrid.adjacent_nodes` keeps the type off its own interface by taking a
  `bool` and doing the conversion internally, which reduces the exposure to the one
  suppressed call inside that method.
- **`MinimapNode.connect`** takes a required `connection_type` that
  `GridNode.connect` does not — a deliberate incompatibility, since a connection
  that does not say how it is traversed cannot be compiled into a movement. Giving
  the parameter a default would satisfy Pyright by permitting exactly what the
  signature exists to forbid.
- **`MapleMinimap.map_area_width` / `map_area_height`** override plain `int` class
  attributes on `Minimap` whose default is the `NotImplemented` sentinel, which the
  base then tests for by `isinstance`. A property overriding a variable is an
  incompatible override whatever it returns; the shape belongs to the base class.
- **`MinimapEdits.name` / `AutoGeneratedFeature.name`** re-declare `Box.name`,
  which is `str | None = None`, as a required `str`: a minimap feature must be
  named. Pyright reports any re-declaration that drops an inherited default,
  regardless of `kw_only`, and the only fix it accepts — giving `name` a default —
  permits exactly the nameless feature the declaration exists to forbid. The root
  cause is `Box`'s shape, which every other Box in the tree depends on.

## "Strongly typed"

The standard new code is written to, and the bar the ratchet is walking the
rest of the repo toward:

- Every parameter and every return annotated, including `-> None`.
- Containers parameterised: `list[str]` not `list`, `dict[str, Box]` not
  `dict`.
- Optionals explicit: `X | None`. No implicit-optional via a `None` default.
- `Any` is a last resort and carries a comment saying why.
- Images and arrays use `numpy.typing.NDArray[np.uint8]`, not bare
  `np.ndarray` — this repo passes screenshots through nearly every layer, and
  bare `ndarray` erases both dtype and intent.
- Structured data crossing a module seam is a `dataclass`, `TypedDict`, or
  `Protocol` — not a bare `dict` whose shape lives only in the reader's head.
- Where [`CONTEXT.md`](../../CONTEXT.md) defines a domain term, prefer the
  precise type over the primitive.

## Editor parity

VS Code's Pylance *is* Pyright — it bundles its own copy and reads the same
`[tool.pyright]` table Pyright's CLI does. That single config table is the
only source of truth for typing rules; a `pyrightconfig.json` must **never**
be added anywhere in this repo; wherever both exist, `pyrightconfig.json`
silently wins over `pyproject.toml`, and editor/hook parity breaks with no
warning.

`.vscode/settings.json` carries the other half of parity:

- `python.analysis.pyrightVersion` pins Pylance to the exact same Pyright
  build the hook runs — currently `1.1.411`, matching `pyright==1.1.411` in
  `requirements-dev.txt`. **Keep these two pins in sync.** `pyright` is the
  one dependency in this repo that is exact-pinned rather than floor-pinned,
  specifically so this pair can't drift apart silently on an unrelated
  `pip install -U`.
- `python.analysis.diagnosticsSource` is set to `"Pylance + Pyright"`.
  Pylance's own diagnostics are a superset of Pyright's; left at its default
  (`"Pylance"`), the editor can show *more* than the hook even at identical
  versions.
- `python.analysis.typeCheckingMode` is deliberately **not** set here. Its
  extension default is `"off"`, and `[tool.pyright]`'s `typeCheckingMode`
  overrides it — but only if nothing in `.vscode/settings.json` fights it.
  Setting it here would silently re-introduce a second source of truth.

## Baseline

Measured 2026-08-31, `pyright==1.1.411`, `.venv` on Python 3.14.7, 193 files
across the fully governed tree (`botting/`, `maple/`, `ml_training/`,
`tests/`, `toolkit/`, `conftest.py`, `paths.py`):

### Pyright error census

| directory | basic | standard | strict |
| --- | ---: | ---: | ---: |
| `<root>` | 1 | 1 | 6 |
| `botting/` | 196 | 198 | 1535 |
| `maple/` | 457 | 470 | 3831 |
| `ml_training/` | 75 | 75 | 1044 |
| `tests/` | 104 | 106 | 2060 |
| `toolkit/` | 29 | 29 | 726 |
| **TOTAL** | **862** | **879** | **9202** |

`basic` → `standard` costs 17 errors repo-wide. **No directory is clean at
`strict`.** `botting/controller/inputs/` — the Strict List's pilot entry —
carries 184 of the 1535 `botting/` strict errors, across all 6 of its files.

### Annotation-gap baseline

#73's original count covered only `botting/`, `maple/`, and `ml_training/`.
Every tree is now governed, so this re-measures across all five plus the
root modules:

| tree | functions | missing return | fn w/ unannotated param | params unannotated |
| --- | ---: | ---: | ---: | ---: |
| `botting/` | 277 | 37 (13%) | 43 (16%) | 65/432 (15%) |
| `maple/` | 505 | 97 (19%) | 67 (13%) | 124/717 (17%) |
| `ml_training/` | 134 | 31 (23%) | 17 (13%) | 21/219 (10%) |
| `tests/` | 322 | 251 (78%) | 192 (60%) | 304/366 (83%) |
| `toolkit/` | 42 | 21 (50%) | 8 (19%) | 37/55 (67%) |
| `<root>` | 4 | 1 (25%) | 1 (25%) | 1/3 (33%) |
| **TOTAL** | **1284** | **438 (34%)** | **328 (26%)** | **552/1792 (31%)** |

`tests/` carries most of the parameter-annotation debt by a wide margin —
largely fixture and `mocker`-typed arguments. Nothing here is a target for a
bulk pass; see [Bulk-fixing pre-existing debt](#the-boy-scout-rule) above.
