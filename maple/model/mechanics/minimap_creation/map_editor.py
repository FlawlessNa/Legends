"""
Controller for the Minimap Editor GUI.

Ties together MapleMinimap, MinimapEditsManager, and the Tkinter view.
Supports two modes:
  - Trail Recording  : combined map-builder (Record | Features | Portals tabs)
  - Pathfinding      : visualise computed paths and optionally execute them
"""

import asyncio
import contextlib
import os
import threading
import time
import tkinter as tk

import cv2
import numpy as np

from botting import controller
from botting.controller import KeyboardInputWrapper
from maple.model.characters.magicians import Magician
from maple.model.mechanics.maple_map import MapleMinimap

from ..movement_mechanics_v2 import MovementHandler
from .map_editor_view import EditorView, PathfindingFrame, TrailRecordingFrame
from .minimap_edits_model import MinimapEdits, MinimapEditsManager, PortalEdge
from .minimap_grid import ConnectionTypes

MOVEMENT_DURATION_LIMIT = 0.4  # seconds

_START_DOT_COLOR = "#ff8800"
_END_DOT_COLOR = "#cc44ff"

_PATH_COLORS: dict = {
    "walk": "green",
    "climb": "#9BEB87",
    ConnectionTypes.JUMP: "yellow",
    ConnectionTypes.JUMP_LEFT: "yellow",
    ConnectionTypes.JUMP_RIGHT: "yellow",
    ConnectionTypes.JUMP_DOWN: "orange",
    ConnectionTypes.FALL_LEFT: "orange",
    ConnectionTypes.FALL_RIGHT: "orange",
    ConnectionTypes.FALL_ANY: "orange",
    ConnectionTypes.TELEPORT_LEFT: "cyan",
    ConnectionTypes.TELEPORT_RIGHT: "cyan",
    ConnectionTypes.TELEPORT_UP: "cyan",
    ConnectionTypes.TELEPORT_DOWN: "cyan",
    ConnectionTypes.IN_MAP_PORTAL: "magenta",
    ConnectionTypes.OUT_MAP_PORTAL: "magenta",
}


class MinimapEditor:
    """
    Opens a Tkinter minimap editor for the given MapleMinimap.
    Blocks until the window is closed; edited MinimapEditsManager
    is then available via self.edits.
    """

    def __init__(
        self,
        minimap: MapleMinimap,
        edits: MinimapEditsManager = None,
        include_character_position: bool = True,
        ign: str | None = None,
        scale: int = 5,
    ):
        self.minimap = minimap
        self.edits = edits or MinimapEditsManager()
        self.scale = scale
        self.ign = ign

        self._latest_actions: KeyboardInputWrapper | None = None
        self._timeline_fig = None
        self._move_stop_event: threading.Event | None = None
        self._map_area_box = None
        self.handle = 0
        self.lock = self.q = None

        try:
            from botting.utilities import client_handler
            from maple import maple_ign_finder

            self.handle = client_handler.get_client_handle(self.ign, maple_ign_finder)
            self.lock = asyncio.Lock()
            self.q = asyncio.Queue()
            if include_character_position:
                self._map_area_box = self.minimap.get_map_area_box(self.handle)
        except ValueError, Exception:
            pass

        # Capture screenshot for background display; measure canvas dimensions on first run
        # (before the first save) so they are persisted and reused on every subsequent load.
        if self.handle != 0 and self._map_area_box is not None:
            try:
                from botting.utilities import take_screenshot

                img = take_screenshot(self.handle, self._map_area_box)
                self._screenshot_bg = img
                self._bg_mode = "screenshot"
                if self.edits.canvas_width is None:
                    self.edits.canvas_height, self.edits.canvas_width = img.shape[:2]
            except Exception as e:
                print(f"Could not capture minimap screenshot: {e}")

        # Build the editor canvas from features at the correct (now saved) dimensions.
        raw = self.edits.build_canvas()
        self.modified_minimap = self.edits.apply_grid_edits(raw, apply_weights=False)

        # Offline fallback when there are no features and no saved dimensions.
        if self.modified_minimap.shape[0] <= 1:
            h, w = self._DEFAULT_CANVAS_SHAPE
            self.modified_minimap = np.zeros((h, w), np.uint8)

        self.movement_handler = MovementHandler(
            self.handle,
            self.minimap,
            self.ign,
            Magician.skills["Teleport"],
        )

        # Background mode: "black" or "screenshot"
        self._bg_mode = "black"
        self._screenshot_bg: np.ndarray | None = None

        # Trail Recording state (no accumulated dots — just start/end markers)
        self._dot_selection_pending: str | None = None
        self._trail_start: tuple[int, int] | None = None
        self._trail_end: tuple[int, int] | None = None
        self._start_marker_id: int | None = None
        self._end_marker_id: int | None = None

        # Pathfinding state
        self.character_marker = None
        self.update_char_pos = include_character_position
        self.start_point = self.end_point = None
        self.previous_path = []
        self.rectangles = {}

        self.root = tk.Tk()
        self.view = EditorView(
            self,
            self.modified_minimap,
            self.save_edits,
            self.movement_handler,
            self.get_to_target,
            scale,
        )

        self.refresh_canvas(self.modified_minimap)
        self.refresh_mode_specific_frame()

        if include_character_position and self._map_area_box is not None:
            self.update_character_position()

        self.root.mainloop()

    _DEFAULT_CANVAS_SHAPE = (
        150,
        200,
    )  # (height, width) fallback: offline + no features

    # ------------------------------------------------------------------
    # Canvas helpers
    # ------------------------------------------------------------------

    def refresh_canvas(self, minimap: np.ndarray) -> None:
        self.view.canvas.delete("all")
        # delete('all') invalidates all item IDs — reset so they get recreated
        self.character_marker = None
        self._start_marker_id = None
        self._end_marker_id = None
        bg = self._get_background_image(minimap)
        self.view.canvas.refresh_canvas(bg)
        self.draw_rectangles_from_features()
        self.draw_portals_from_edits()

    def _get_background_image(self, minimap: np.ndarray) -> np.ndarray:
        if self._bg_mode == "screenshot" and self._screenshot_bg is not None:
            return self._screenshot_bg
        display = minimap.copy().astype(np.uint8)
        display[display.nonzero()] = 255
        return display

    def set_background_mode(self, mode: str) -> None:
        assert mode in ("black", "screenshot")
        self._bg_mode = mode
        if mode == "screenshot":
            self._capture_screenshot_background()
        self.refresh_canvas(self.modified_minimap)

    def _capture_screenshot_background(self) -> None:
        if self._map_area_box is None or self.handle == 0:
            print("No game client connected — screenshot background unavailable.")
            return
        try:
            from botting.utilities import take_screenshot

            self._screenshot_bg = take_screenshot(self.handle, self._map_area_box)
        except Exception as e:
            print(f"Screenshot capture failed: {e}")

    def draw_rectangles_from_features(self) -> None:
        self._delete_rectangles()
        for feature in self.edits.features:
            self.rectangles[feature.name] = self.view.canvas.create_rectangle(
                feature.left * self.scale,
                feature.top * self.scale,
                feature.right * self.scale,
                feature.bottom * self.scale,
                outline="green",
            )

    def draw_rectangle_in_construction(self, name: str) -> None:
        self.view.canvas.delete(self.rectangles.get(name))
        feature = next(f for f in self.edits.features if f.name == name)
        self.rectangles[name] = self.view.canvas.create_rectangle(
            feature.left * self.scale,
            feature.top * self.scale,
            feature.right * self.scale,
            feature.bottom * self.scale,
            outline="orange",
        )

    def draw_portals_from_edits(self) -> None:
        for portal in self.edits.portals:
            sx, sy = portal.source[0] * self.scale, portal.source[1] * self.scale
            tx, ty = portal.target[0] * self.scale, portal.target[1] * self.scale
            self.view.canvas.create_line(
                sx, sy, tx, ty, fill="cyan", width=2, arrow=tk.LAST
            )
            if portal.bidirectional:
                self.view.canvas.create_line(
                    tx, ty, sx, sy, fill="cyan", width=2, arrow=tk.LAST
                )

    def _delete_rectangles(self) -> None:
        for rect in self.rectangles.values():
            self.view.canvas.delete(rect)
        self.rectangles = {}

    # ------------------------------------------------------------------
    # Mode frame management
    # ------------------------------------------------------------------

    def refresh_mode_specific_frame(self) -> None:
        if self.view.get_current_mode() == "Trail Recording":
            sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
            sub.refresh_feature_list(self.edits.names)
            sub.feature_listbox.bind("<<ListboxSelect>>", self.on_feature_select)
            self._refresh_scale_display(sub)
            self._refresh_title_display(sub)

    def _refresh_scale_display(self, sub: TrailRecordingFrame) -> None:
        sx = self.edits.scale_x
        sy = self.edits.scale_y
        sx_str = f"{sx:.6f}" if sx is not None else "—"
        sy_str = f"{sy:.6f}" if sy is not None else "—"
        sub.calib_result_label.config(text=f"scale_x: {sx_str}   scale_y: {sy_str}")

    def _refresh_title_display(self, sub: TrailRecordingFrame) -> None:
        path = self.edits.title_img_path
        if path:
            sub.title_status_label.config(text=f"Saved: {path}")

    # ------------------------------------------------------------------
    # Feature list: select, update, delete
    # ------------------------------------------------------------------

    def on_feature_select(self, _event) -> None:
        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        selection = sub.feature_listbox.curselection()
        if not selection:
            return
        name = sub.feature_listbox.get(selection[0])
        feature = next((f for f in self.edits.features if f.name == name), None)
        if feature is None:
            return
        self.refresh_canvas(self.modified_minimap)
        self.draw_rectangle_in_construction(name)
        self._populate_edit_fields(sub, feature)

    def _populate_edit_fields(
        self, sub: TrailRecordingFrame, feature: MinimapEdits
    ) -> None:
        def _set(entry, val):
            entry.delete(0, tk.END)
            entry.insert(0, str(val))

        _set(sub.edit_name_entry, feature.name)
        _set(sub.edit_left_entry, feature.left)
        _set(sub.edit_right_entry, feature.right)
        _set(sub.edit_top_entry, feature.top)
        _set(sub.edit_bottom_entry, feature.bottom)
        _set(sub.edit_weight_entry, feature.weight)
        _set(sub.edit_edge_threshold_entry, feature.edge_threshold)
        _set(sub.edit_offset_x, feature.offset[0] if feature.offset else 0)
        _set(sub.edit_offset_y, feature.offset[1] if feature.offset else 0)
        _set(
            sub.edit_rotation_entry,
            ",".join(str(i) for i in (feature.rotation_indexes or [])),
        )
        sub.edit_walkable_var.set(feature.walkable)
        sub.edit_avoid_right_var.set(feature.avoid_right_edge)
        sub.edit_avoid_left_var.set(feature.avoid_left_edge)
        sub.edit_no_jump_var.set(feature.no_jump_connections_from_endpoints)

    @staticmethod
    def _read_edit_fields(sub: TrailRecordingFrame) -> dict:
        return {
            "name": sub.edit_name_entry.get(),
            "left": int(sub.edit_left_entry.get()),
            "right": int(sub.edit_right_entry.get()),
            "top": int(sub.edit_top_entry.get()),
            "bottom": int(sub.edit_bottom_entry.get()),
            "offset": (
                int(sub.edit_offset_x.get() or 0),
                int(sub.edit_offset_y.get() or 0),
            ),
            "weight": int(sub.edit_weight_entry.get() or 1),
            "walkable": sub.edit_walkable_var.get(),
            "rotation_indexes": [
                int(i.strip())
                for i in sub.edit_rotation_entry.get().split(",")
                if i.strip()
            ],
            "avoid_right_edge": sub.edit_avoid_right_var.get(),
            "avoid_left_edge": sub.edit_avoid_left_var.get(),
            "edge_threshold": int(sub.edit_edge_threshold_entry.get() or 0),
            "no_jump_connections_from_endpoints": sub.edit_no_jump_var.get(),
        }

    def update_feature(self, sub: TrailRecordingFrame) -> None:
        selection = sub.feature_listbox.curselection()
        if not selection:
            print("Select a feature from the list first.")
            return
        old_name = sub.feature_listbox.get(selection[0])
        try:
            data = self._read_edit_fields(sub)
            new_name = data["name"].strip()
            assert new_name, "Feature name must not be empty"
            if new_name != old_name and new_name in self.edits.names:
                print(
                    f"Error: feature '{new_name}' already exists. Choose a different name."
                )
                return
            feature = MinimapEdits(**data)
            idx = self.edits.names.index(old_name)
            self.edits.features[idx] = feature
            print(f"Feature updated: {feature}")
            self._rebuild_modified_minimap()
            self.refresh_canvas(self.modified_minimap)
            sub.refresh_feature_list(self.edits.names)
            new_idx = self.edits.names.index(new_name)
            sub.feature_listbox.selection_set(new_idx)
            self.draw_rectangle_in_construction(new_name)
        except Exception as e:
            print(f"Error updating feature: {e}")

    def delete_feature(self, sub: TrailRecordingFrame) -> None:
        selection = sub.feature_listbox.curselection()
        if not selection:
            print("Select a feature from the list first.")
            return
        name = sub.feature_listbox.get(selection[0])
        idx = self.edits.names.index(name)
        self.edits.features.pop(idx)
        print(f"Feature deleted: {name}")
        self._rebuild_modified_minimap()
        self.refresh_canvas(self.modified_minimap)
        sub.refresh_feature_list(self.edits.names)

    # ------------------------------------------------------------------
    # Portal registration
    # ------------------------------------------------------------------

    def register_portal(self, frame: TrailRecordingFrame) -> None:
        try:
            src = (int(frame.portal_src_x.get()), int(frame.portal_src_y.get()))
            tgt = (int(frame.portal_tgt_x.get()), int(frame.portal_tgt_y.get()))
            bidir = frame.portal_bidir_var.get()
            portal = PortalEdge(source=src, target=tgt, bidirectional=bidir)
            self.edits.portals.append(portal)
            print(f"Portal registered: {portal}")
            self.refresh_canvas(self.modified_minimap)
        except Exception as e:
            print(f"Error registering portal: {e}")

    def _rebuild_modified_minimap(self) -> None:
        raw = self.edits.build_canvas()
        self.modified_minimap = self.edits.apply_grid_edits(raw, apply_weights=False)

    # ------------------------------------------------------------------
    # Minimap title image capture
    # ------------------------------------------------------------------

    def capture_title_image(self) -> None:
        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        if not isinstance(sub, TrailRecordingFrame):
            return
        if self.handle == 0:
            sub.title_status_label.config(text="Error: no game client connected.")
            return
        try:
            img = self.minimap.get_minimap_title_img(self.handle)
        except Exception as e:
            sub.title_status_label.config(text=f"Error: {e}")
            return
        if img is None:
            sub.title_status_label.config(
                text="Failed: minimap must be in Full display mode."
            )
            return

        self._pending_title_img = img

        from PIL import Image, ImageTk

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        scale = max(1, 48 // img_rgb.shape[0])  # ensure at least ~48px tall
        pil = Image.fromarray(img_rgb).resize(
            (img_rgb.shape[1] * scale, img_rgb.shape[0] * scale),
            Image.NEAREST,
        )
        photo = ImageTk.PhotoImage(pil)
        sub._title_preview_photo = photo  # keep reference
        sub.title_preview_label.config(image=photo, text="")
        sub.confirm_title_btn.config(state=tk.NORMAL)
        sub.retake_title_btn.config(state=tk.NORMAL)
        sub.title_status_label.config(text="Preview ready — confirm to save.")

    def confirm_title_image(self) -> None:
        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        if not isinstance(sub, TrailRecordingFrame):
            return
        img = getattr(self, "_pending_title_img", None)
        if img is None:
            return
        from paths import ROOT

        rel_path = f"maple/assets/detection_images/{self.minimap.map_name}Minimap.png"
        abs_path = os.path.join(ROOT, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        cv2.imwrite(abs_path, img)
        self.edits.title_img_path = rel_path
        self._pending_title_img = None
        sub.confirm_title_btn.config(state=tk.DISABLED)
        sub.retake_title_btn.config(state=tk.DISABLED)
        sub.title_status_label.config(text=f"Saved: {rel_path}")

    # ------------------------------------------------------------------
    # Scale calibration
    # ------------------------------------------------------------------

    def start_scale_calibration(self, kind: str) -> None:
        assert kind in ("walking", "climbing")
        if self._map_area_box is None or self.handle == 0:
            print("Cannot calibrate: no game client connected.")
            return

        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        try:
            duration = float(sub.calib_duration_entry.get())
            speed_mod = float(sub.calib_speed_entry.get())
        except ValueError:
            print("Invalid duration or speed modifier.")
            return

        try:
            start_pos = self.minimap.get_character_positions(
                self.handle, map_area_box=self._map_area_box
            ).pop()
        except KeyError, IndexError:
            print(
                "Cannot detect character position — is the character visible on the minimap?"
            )
            return

        try:
            import win32gui

            win32gui.SetForegroundWindow(self.handle)
        except Exception as e:
            print(f"Could not focus game window: {e}")

        start_time = time.time()
        status_lbl = sub.calib_status_label
        walk_btn = sub.calib_walk_btn
        climb_btn = sub.calib_climb_btn

        walk_btn.config(state=tk.DISABLED)
        climb_btn.config(state=tk.DISABLED)

        def _finish():
            try:
                end_pos = self.minimap.get_character_positions(
                    self.handle, map_area_box=self._map_area_box
                ).pop()
            except KeyError, IndexError:
                if status_lbl.winfo_exists():
                    status_lbl.config(text="Error: could not read end position.")
                walk_btn.config(state=tk.NORMAL)
                climb_btn.config(state=tk.NORMAL)
                return

            elapsed = time.time() - start_time
            walk_speed_vr = 125.0 * speed_mod
            if kind == "walking":
                delta = abs(end_pos[0] - start_pos[0])
                scale = delta / (walk_speed_vr * elapsed) if elapsed > 0 else 0.0
                self.edits.scale_x = scale
                attr = "scale_x"
            else:
                delta = abs(end_pos[1] - start_pos[1])
                scale = delta / (walk_speed_vr * elapsed) if elapsed > 0 else 0.0
                self.edits.scale_y = scale
                attr = "scale_y"

            if status_lbl.winfo_exists():
                status_lbl.config(
                    text=f"Done!  {attr} = {scale:.6f}  (Δ={delta}px, t={elapsed:.2f}s)"
                )
            self._refresh_scale_display(sub)
            walk_btn.config(state=tk.NORMAL)
            climb_btn.config(state=tk.NORMAL)

        self.root.after(int(duration * 1000), _finish)

        def _tick(remaining: int):
            if status_lbl.winfo_exists():
                label = "walk" if kind == "walking" else "climb"
                status_lbl.config(text=f"Recording {label}... {remaining}s")
            if remaining > 0:
                self.root.after(1000, lambda: _tick(remaining - 1))

        _tick(int(duration))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_edits(self) -> None:
        self.edits.to_json(self.minimap.map_name)
        print(f"Edits saved for map: {self.minimap.map_name}")

    # ------------------------------------------------------------------
    # Character position overlay
    # ------------------------------------------------------------------

    def update_character_position(self) -> None:
        if not self.update_char_pos or self._map_area_box is None:
            return
        try:
            pos = self.minimap.get_character_positions(
                self.handle, map_area_box=self._map_area_box
            ).pop()
            coords = (
                pos[0] * self.scale,
                pos[1] * self.scale,
                (pos[0] + 1) * self.scale,
                (pos[1] + 1) * self.scale,
            )
            if self.character_marker is None:
                self.character_marker = self.view.canvas.create_rectangle(
                    *coords, fill="red"
                )
            else:
                self.view.canvas.coords(self.character_marker, *coords)

            if self.view.get_current_mode() == "Pathfinding":
                frame: PathfindingFrame = (
                    self.view.controls_frame.mode_specific_subframe
                )
                if isinstance(frame, PathfindingFrame) and frame.use_char_pos_var.get():
                    x, y = int(pos[0]), int(pos[1])
                    if (x, y) != self.start_point:
                        self.start_point = (x, y)
                        frame.start_pos_label.config(text=f"Start Position: ({x}, {y})")
                        self._calculate_and_display_path()
        except KeyError, IndexError:
            pass
        self.root.after(100, self.update_character_position)

    # ------------------------------------------------------------------
    # Trail Recording
    # ------------------------------------------------------------------

    def begin_dot_selection(self, which: str) -> None:
        assert which in ("start", "end")
        if self._map_area_box is not None:
            try:
                pos = self.minimap.get_character_positions(
                    self.handle, map_area_box=self._map_area_box
                ).pop()
                self._set_trail_point(which, int(pos[0]), int(pos[1]))
                self._maybe_return_focus()
                return
            except KeyError, IndexError:
                pass
        # Fallback: wait for canvas click
        self._dot_selection_pending = which

    def _maybe_return_focus(self) -> None:
        if self.handle == 0:
            return
        sub = self.view.controls_frame.mode_specific_subframe
        if not isinstance(sub, TrailRecordingFrame) or not sub.return_focus_var.get():
            return
        try:
            import win32gui

            win32gui.SetForegroundWindow(self.handle)
        except Exception as e:
            print(f"Could not return focus to game: {e}")

    def on_trail_canvas_click(self, x: int, y: int) -> None:
        if self._dot_selection_pending is None:
            return
        which = self._dot_selection_pending
        self._dot_selection_pending = None
        self._set_trail_point(which, x, y)

    def _set_trail_point(self, which: str, x: int, y: int) -> None:
        color = _START_DOT_COLOR if which == "start" else _END_DOT_COLOR
        if which == "start":
            if self._start_marker_id is not None:
                self.view.canvas.delete(self._start_marker_id)
            self._trail_start = (x, y)
            self._start_marker_id = self.view.canvas.draw_point(x, y, color)
        else:
            if self._end_marker_id is not None:
                self.view.canvas.delete(self._end_marker_id)
            self._trail_end = (x, y)
            self._end_marker_id = self.view.canvas.draw_point(x, y, color)
        self._refresh_selection_label()

    def _refresh_selection_label(self) -> None:
        if self.view.get_current_mode() != "Trail Recording":
            return
        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        s = str(self._trail_start) if self._trail_start is not None else "–"
        e = str(self._trail_end) if self._trail_end is not None else "–"
        sub.update_selection_label(s, e)

    def mark_trail_segment(self, name: str) -> None:
        if self._trail_start is None or self._trail_end is None:
            print("Select both a start and an end point first.")
            return
        x1, y1 = self._trail_start
        x2, y2 = self._trail_end
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        if dx >= dy:  # wider than tall → platform
            med_y = round((y1 + y2) / 2)
            left, right, top, bottom = min(x1, x2), max(x1, x2), med_y, med_y
            kind = "platform"
        else:  # taller than wide → ladder
            med_x = round((x1 + x2) / 2)
            left, right, top, bottom = med_x, med_x, min(y1, y2), max(y1, y2)
            kind = "ladder"

        feature_name = name.strip() or f"{kind}_{len(self.edits.features) + 1}"
        if name.strip() and feature_name in self.edits.names:
            print(
                f"Error: feature '{feature_name}' already exists. Choose a different name."
            )
            return
        feature = MinimapEdits(
            name=feature_name,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
        )
        if feature_name in self.edits.names:
            self.edits.features[self.edits.names.index(feature_name)] = feature
        else:
            self.edits.features.append(feature)

        print(f"Feature marked: {feature}")
        self._rebuild_modified_minimap()
        self.refresh_canvas(self.modified_minimap)
        self._trail_start = self._trail_end = None
        self._refresh_selection_label()
        sub: TrailRecordingFrame = self.view.controls_frame.mode_specific_subframe
        if isinstance(sub, TrailRecordingFrame):
            sub.refresh_feature_list(self.edits.names)

    # ------------------------------------------------------------------
    # Pathfinding mode
    # ------------------------------------------------------------------

    def update_start_point(self, x: int, y: int) -> None:
        self.start_point = (x, y)
        self._calculate_and_display_path()

    def update_end_point(self, x: int, y: int) -> None:
        self.end_point = (x, y)
        self._calculate_and_display_path()

    def _calculate_and_display_path(self) -> None:
        if self.start_point is None or self.end_point is None:
            return
        frame: PathfindingFrame = self.view.controls_frame.mode_specific_subframe
        assert isinstance(frame, PathfindingFrame)
        kwargs = frame.get_grid_kwargs()
        grid = self.minimap.generate_grid(**kwargs)
        path = self.movement_handler.compute_path(
            self.start_point, self.end_point, grid
        )
        if frame.print_path:
            print(f"Path:\n{chr(10).join(map(str, path))}")
        movements = self.movement_handler.path_into_movements(path, grid)
        if frame.print_movements:
            print(f"Movements:\n{chr(10).join(map(str, movements))}")
        frame.update_movement_display(movements, grid.speed)
        actions = self.movement_handler.movements_into_action(movements, grid)
        self._latest_actions = actions
        if frame.print_actions:
            print(f"Actions:\n{actions}")
        self._draw_path_on_canvas(path, self.start_point, self.end_point)
        self._update_timeline()

    def _draw_path_on_canvas(
        self,
        path: tuple,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        """Clear the previous path and paint the new one. Must run on the main thread."""
        endpoints = {start, end}
        for node in self.previous_path:
            if (node.x, node.y) not in endpoints:
                bg_color = (
                    "white" if self.modified_minimap[node.y, node.x] != 0 else "black"
                )
                self.view.canvas.draw_point(node.x, node.y, bg_color)
        for i, node in enumerate(path):
            if (node.x, node.y) in endpoints:
                continue
            if i == 0:
                color = _PATH_COLORS["walk"]
            else:
                prev = path[i - 1]
                if node in prev.connections:
                    color = _PATH_COLORS.get(prev.get_connection_type(node), "green")
                else:
                    color = (
                        _PATH_COLORS["walk"]
                        if node.x != prev.x
                        else _PATH_COLORS["climb"]
                    )
            self.view.canvas.draw_point(node.x, node.y, color)
        if self.character_marker is not None:
            self.view.canvas.tag_raise(self.character_marker)
        self.previous_path = path

    def _on_move_display(
        self,
        pos: tuple[int, int],
        end_point: tuple[int, int],
        path: tuple,
        actions: KeyboardInputWrapper,
    ) -> None:
        """UI refresh scheduled by the move loop after each recompute. Main thread only."""
        self._draw_path_on_canvas(path, pos, end_point)
        self._latest_actions = actions
        self._update_timeline()

    def _update_timeline(self) -> None:
        if self._latest_actions is None:
            return
        from toolkit.movement_timeline import visualize

        title = f"{self.minimap.map_name}:  {self.start_point} → {self.end_point}"
        self._timeline_fig = visualize(
            self._latest_actions, title=title, block=False, fig=self._timeline_fig
        )

    def show_timeline(self) -> None:
        if self._latest_actions is None:
            print("No actions computed yet — set a start and end point first.")
            return
        from toolkit.movement_timeline import visualize

        title = f"{self.minimap.map_name}:  {self.start_point} → {self.end_point}"
        print("Opening timeline — editor resumes when the window is closed.")
        visualize(self._latest_actions, title=title)

    def get_to_target(self) -> None:
        if self.end_point is None:
            print("No end point set.")
            return

        frame: PathfindingFrame = self.view.controls_frame.mode_specific_subframe
        assert isinstance(frame, PathfindingFrame)
        grid_kwargs = frame.get_grid_kwargs()
        end_point = self.end_point

        def _run():
            import pythoncom

            pythoncom.CoInitialize()
            try:

                async def _main_loop():
                    lock = asyncio.Lock()
                    q: asyncio.Queue = asyncio.Queue()

                    async def _execute_actions():
                        while True:
                            action = await q.get()
                            if action is None:
                                break
                            task = asyncio.create_task(action.send())
                            task.add_done_callback(lambda _: lock.release())
                        print("Finished executing actions.")
                        controller.release_all(self.handle)

                    async def _recompute_actions():
                        while True:
                            print("Waiting on Lock")
                            await lock.acquire()
                            print("Lock Acquired - Recomputing")
                            try:
                                pos = self.minimap.get_character_positions(
                                    self.handle, map_area_box=self._map_area_box
                                ).pop()
                            except KeyError, IndexError:
                                print("Could not detect character position — stopping.")
                                await q.put(None)
                                break
                            grid = self.minimap.generate_grid(**grid_kwargs)
                            path = self.movement_handler.compute_path(
                                pos, end_point, grid
                            )
                            if len(path) <= 3:
                                print("Stopping Recompute - Reached Destination")
                                await q.put(None)
                                break
                            movements = self.movement_handler.path_into_movements(
                                path, grid
                            )
                            actions = self.movement_handler.movements_into_action(
                                movements, grid, MOVEMENT_DURATION_LIMIT
                            )
                            await q.put(actions)
                        print("Finished re-computing actions.")

                    await asyncio.gather(_execute_actions(), _recompute_actions())

                asyncio.run(_main_loop())
                print("Done!")
            finally:
                pythoncom.CoUninitialize()

        threading.Thread(target=_run, daemon=True).start()

    def toggle_move(self, button: tk.Button) -> None:
        if self._move_stop_event is not None and not self._move_stop_event.is_set():
            self._move_stop_event.set()
            button.config(text="Move")
        else:
            frame: PathfindingFrame = self.view.controls_frame.mode_specific_subframe
            assert isinstance(frame, PathfindingFrame)
            grid_kwargs = frame.get_grid_kwargs()
            self._move_stop_event = threading.Event()
            button.config(text="Stop Moving")
            self._start_move_loop(button, grid_kwargs)

    def _start_move_loop(self, button: tk.Button, grid_kwargs: dict) -> None:
        stop_event = self._move_stop_event

        def _run():
            import pythoncom

            pythoncom.CoInitialize()
            try:

                async def _main_loop():
                    current_task: asyncio.Task | None = None
                    end_point = self.minimap.random_point()
                    print(f"Move: first target = {end_point}")

                    async def _replace_action(
                        new_actions: KeyboardInputWrapper,
                    ) -> asyncio.Task:
                        nonlocal current_task
                        if current_task is not None and not current_task.done():
                            current_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await current_task
                            controller.release_all(self.handle)
                        return asyncio.create_task(new_actions.send())

                    try:
                        while not stop_event.is_set():
                            try:
                                pos = self.minimap.get_character_positions(
                                    self.handle, map_area_box=self._map_area_box
                                ).pop()
                            except KeyError, IndexError:
                                await asyncio.sleep(0.1)
                                continue

                            grid = self.minimap.generate_grid(**grid_kwargs)
                            path = self.movement_handler.compute_path(
                                pos, end_point, grid
                            )
                            if len(path) <= 3:
                                end_point = self.minimap.random_point()
                                print(f"Move: new target = {end_point}")
                                path = self.movement_handler.compute_path(
                                    pos, end_point, grid
                                )
                            movements = self.movement_handler.path_into_movements(
                                path, grid
                            )
                            actions = self.movement_handler.movements_into_action(
                                movements, grid, MOVEMENT_DURATION_LIMIT
                            )
                            if actions is None:
                                await asyncio.sleep(0.1)
                                continue

                            current_task = await _replace_action(actions)
                            self.root.after(
                                0,
                                lambda _pos=pos, _ep=end_point, _p=path, _a=actions: (
                                    self._on_move_display(_pos, _ep, _p, _a)
                                ),
                            )
                            await asyncio.sleep(MOVEMENT_DURATION_LIMIT)
                    finally:
                        if current_task is not None and not current_task.done():
                            current_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await current_task
                        controller.release_all(self.handle)

                asyncio.run(_main_loop())
            finally:
                pythoncom.CoUninitialize()
                self._move_stop_event = None
                self.root.after(
                    0,
                    lambda: (
                        button.config(text="Move") if button.winfo_exists() else None
                    ),
                )

        threading.Thread(target=_run, daemon=True).start()
