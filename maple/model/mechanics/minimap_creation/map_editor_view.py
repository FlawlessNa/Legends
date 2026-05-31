"""
View classes for the Minimap Editor GUI.

Two modes:
  - Trail Recording  : combined map-builder with three tabs
                         Record   – Set Start/End Dot → Mark as Feature
                         Features – List, edit, and delete registered features
                         Portals  – Add portal connections between nodes
  - Pathfinding      : visualise computed paths and optionally execute them
"""

from abc import ABC, abstractmethod
from PIL import Image, ImageTk
import cv2
import numpy as np
import tkinter as tk
import tkinter.ttk as ttk


# ---------------------------------------------------------------------------
# Top-level frame
# ---------------------------------------------------------------------------

class EditorView(ttk.Frame):
    def __init__(
        self,
        editor,
        edited_minimap: np.ndarray,
        save: callable,
        path_handler,
        on_send_actions: callable,
        scale: int = 5,
        *args,
        **kwargs,
    ):
        self.editor = editor
        self.editor.root.title("Minimap Editor")
        super().__init__(self.editor.root)
        self.pack(fill=tk.BOTH, expand=True)

        self.controls_frame = ControlsFrame(self, save, path_handler, on_send_actions)
        self.canvas = EditableCanvas(
            self,
            scale,
            *args,
            width=edited_minimap.shape[1] * scale,
            height=edited_minimap.shape[0] * scale,
            **kwargs,
        )

        self.coord_label = tk.Label(self.editor.root, text="Coordinates: (0, 0)")
        self.coord_label.pack(side=tk.BOTTOM)

    def get_current_mode(self) -> str:
        return self.controls_frame.selector_subframe.current_mode.get()


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class EditableCanvas(tk.Canvas):
    master: EditorView

    def __init__(self, parent: EditorView, scale: int, *args, width, height, **kwargs):
        super().__init__(parent, width=width, height=height, *args, **kwargs)
        self.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scale = scale

        self.bind("<ButtonPress-1>", self.on_button_press)
        self.bind("<B1-Motion>", self.on_mouse_drag)
        self.bind("<ButtonRelease-1>", self.on_button_release)
        self.bind("<Motion>", self.on_mouse_move)
        self.bind_all("<KeyPress>", self.on_key_press)

        self.image_displayed = None
        self.start_point = self.end_point = None
        self.start_point_id = self.end_point_id = None

    def get_current_mode(self) -> str:
        return self.master.get_current_mode()

    def get_cursor_pos(self, event):
        return self.canvasx(event.x) // self.scale, self.canvasy(event.y) // self.scale

    def refresh_canvas(self, img: np.ndarray) -> None:
        if len(img.shape) == 2:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        scaled = pil_img.resize(
            (img_rgb.shape[1] * self.scale, img_rgb.shape[0] * self.scale),
            Image.NEAREST,  # noqa
        )
        self.image_displayed = ImageTk.PhotoImage(scaled)
        self.create_image(0, 0, image=self.image_displayed, anchor=tk.NW)

    def draw_point(self, x, y, color) -> int:
        s = self.scale
        return self.create_rectangle(
            x * s, y * s, (x + 1) * s, (y + 1) * s,
            fill=color, outline=color,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_button_press(self, event):
        mode = self.get_current_mode()
        x, y = self.get_cursor_pos(event)

        if mode == "Trail Recording":
            self.master.editor.on_trail_canvas_click(int(x), int(y))

        elif mode == "Pathfinding":
            if event.state & 0x0004:  # Ctrl → end point
                if self.end_point_id is not None:
                    self.delete(self.end_point_id)
                self.end_point = (x, y)
                self.end_point_id = self.draw_point(x, y, "blue")
                self.master.controls_frame.mode_specific_subframe.update_end_pos_label(x, y)
            else:
                if self.start_point_id is not None:
                    self.delete(self.start_point_id)
                self.start_point = (x, y)
                self.start_point_id = self.draw_point(x, y, "red")
                self.master.controls_frame.mode_specific_subframe.update_start_pos_label(x, y)

    def on_mouse_drag(self, event):
        self.on_mouse_move(event)

    def on_button_release(self, event):
        pass

    def on_mouse_move(self, event):
        cur_x = self.canvasx(event.x) // self.scale
        cur_y = self.canvasy(event.y) // self.scale
        self.master.coord_label.config(text=f"Coordinates: ({cur_x:.0f}, {cur_y:.0f})")

    def on_key_press(self, event):
        if self.get_current_mode() == "Pathfinding":
            if event.keysym in ["Left", "Right", "Up", "Down"]:
                if event.state & 0x0004:
                    if self.end_point is not None:
                        self.move_point(event.keysym, "blue", "end")
                else:
                    if self.start_point is not None:
                        self.move_point(event.keysym, "red", "start")

    def move_point(self, direction, color, point_type):
        if point_type == "start":
            x, y = self.start_point
            point_id = self.start_point_id
        else:
            x, y = self.end_point
            point_id = self.end_point_id
        dx, dy = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}[direction]
        x, y = x + dx, y + dy
        self.delete(point_id)
        if point_type == "start":
            self.start_point = (x, y)
            self.start_point_id = self.draw_point(x, y, color)
            self.master.controls_frame.mode_specific_subframe.update_start_pos_label(x, y)
        else:
            self.end_point = (x, y)
            self.end_point_id = self.draw_point(x, y, color)
            self.master.controls_frame.mode_specific_subframe.update_end_pos_label(x, y)


# ---------------------------------------------------------------------------
# Controls panel
# ---------------------------------------------------------------------------

class ControlsFrame(ttk.Frame):
    master: EditorView

    def __init__(
        self,
        parent,
        edits_saver: callable,
        path_handler,
        on_send_actions: callable,
    ):
        super().__init__(parent)
        self.edits_saver = edits_saver
        self.path_handler = path_handler
        self._on_send_actions = on_send_actions
        self.pack(side=tk.RIGHT, fill=tk.Y)
        self.selector_subframe = _ModeSelectionSubFrame(self)
        self.mode_specific_subframe = None
        self.update_mode_dependent_frame(self.selector_subframe.current_mode.get())

    def update_mode_dependent_frame(self, curr_mode: str) -> None:
        if self.mode_specific_subframe is not None:
            for widget in self.mode_specific_subframe.winfo_children():
                widget.destroy()
            self.mode_specific_subframe.destroy()

        mode_class = {
            "Trail Recording": TrailRecordingFrame,
            "Pathfinding":     PathfindingFrame,
        }[curr_mode]

        self.mode_specific_subframe: _ModeDependentFrame = mode_class(
            self,
            save_edits=self.edits_saver,
            path_handler=self.path_handler,
            on_send_actions=self._on_send_actions,
        )
        self.mode_specific_subframe.create_widgets()
        if hasattr(self.master.editor, 'view'):
            self.master.editor.refresh_mode_specific_frame()


class _ModeSelectionSubFrame(ttk.Frame):
    master: ControlsFrame
    _MODES = ["Trail Recording", "Pathfinding"]

    def __init__(self, parent: ControlsFrame):
        super().__init__(parent)
        self.pack(side=tk.TOP, anchor=tk.W)
        self.current_mode = tk.StringVar(value=self._MODES[0])
        ttk.Label(self, text="Select Mode:").pack(side=tk.TOP, anchor=tk.W)
        for mode in self._MODES:
            tk.Radiobutton(
                self,
                text=mode,
                variable=self.current_mode,
                value=mode,
                command=self.on_mode_change,
            ).pack(anchor=tk.W)

    def on_mode_change(self):
        self.master.update_mode_dependent_frame(self.current_mode.get())


class _ModeDependentFrame(ttk.Frame, ABC):
    master: ControlsFrame

    def __init__(self, parent: ControlsFrame, **kwargs):
        super().__init__(parent)
        self.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    @abstractmethod
    def create_widgets(self):
        pass


# ---------------------------------------------------------------------------
# Trail Recording mode  (Record | Features | Portals)
# ---------------------------------------------------------------------------

class TrailRecordingFrame(_ModeDependentFrame):
    """
    Combined map-builder mode with three notebook tabs.
    """

    def __init__(self, parent: ControlsFrame, **kwargs):
        super().__init__(parent)

        # --- state variables ---
        self.return_focus_var     = tk.BooleanVar(value=True)
        self.bg_var               = tk.StringVar(value="black")
        self.edit_walkable_var    = tk.BooleanVar(value=True)
        self.edit_avoid_right_var = tk.BooleanVar(value=True)
        self.edit_avoid_left_var  = tk.BooleanVar(value=True)
        self.edit_no_jump_var     = tk.BooleanVar(value=False)
        self.portal_bidir_var     = tk.BooleanVar(value=False)

        # --- always-visible widgets (gridded in create_widgets) ---
        self.return_focus_cb = ttk.Checkbutton(
            self, text="Return focus to game after Set Dot",
            variable=self.return_focus_var,
        )
        self.bg_black_rb = tk.Radiobutton(
            self, text="Black", variable=self.bg_var, value="black",
            command=self._on_bg_change,
        )
        self.bg_screenshot_rb = tk.Radiobutton(
            self, text="Screenshot", variable=self.bg_var, value="screenshot",
            command=self._on_bg_change,
        )

        # --- notebook ---
        self.notebook      = ttk.Notebook(self)
        self._record_tab   = ttk.Frame(self.notebook)
        self._features_tab = ttk.Frame(self.notebook)
        self._portals_tab  = ttk.Frame(self.notebook)
        self.notebook.add(self._record_tab,   text="Record")
        self.notebook.add(self._features_tab, text="Features")
        self.notebook.add(self._portals_tab,  text="Portals")

        self._build_record_tab()
        self._build_features_tab()
        self._build_portals_tab()

        self.save_button = tk.Button(
            self, text="Save Edits",
            command=lambda: self.master.master.editor.save_edits(),
        )

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_record_tab(self):
        t = self._record_tab
        t.columnconfigure(1, weight=1)

        self.start_btn = tk.Button(
            t, text="Set Start Dot",
            command=lambda: self.master.master.editor.begin_dot_selection("start"),
        )
        self.end_btn = tk.Button(
            t, text="Set End Dot",
            command=lambda: self.master.master.editor.begin_dot_selection("end"),
        )
        self.sel_label = tk.Label(t, text="Start: –   End: –", font=("", 8))
        self.feature_name_entry = tk.Entry(t)
        self.mark_btn = tk.Button(
            t, text="Mark as Feature",
            command=lambda: self.master.master.editor.mark_trail_segment(
                self.feature_name_entry.get()
            ),
        )

        self.start_btn.grid(row=0, column=0, sticky=tk.EW, padx=(0, 2), pady=(4, 0))
        self.end_btn.grid(row=0, column=1, sticky=tk.EW, pady=(4, 0))
        self.sel_label.grid(row=1, column=0, columnspan=2, sticky=tk.W)
        tk.Label(t, text="Name:").grid(row=2, column=0, sticky=tk.W)
        self.feature_name_entry.grid(row=2, column=1, sticky=tk.EW)
        self.mark_btn.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=4)

    def _build_features_tab(self):
        t = self._features_tab
        t.columnconfigure(0, weight=1)
        t.rowconfigure(0, weight=1)

        # Listbox + scrollbar
        lf = ttk.Frame(t)
        lf.grid(row=0, column=0, sticky=tk.NSEW, pady=(2, 4))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.feature_listbox = tk.Listbox(
            lf, height=6, selectmode=tk.SINGLE, exportselection=False,
        )
        self.feature_listbox.grid(row=0, column=0, sticky=tk.NSEW)
        _sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.feature_listbox.yview)
        _sb.grid(row=0, column=1, sticky=tk.NS)
        self.feature_listbox.config(yscrollcommand=_sb.set)

        # Edit fields
        ef = ttk.LabelFrame(t, text="Edit Selected", padding=4)
        ef.grid(row=1, column=0, sticky=tk.EW)
        ef.columnconfigure(1, weight=1)

        _simple = [
            ("Name:",           "edit_name_entry",           None),
            ("Left:",           "edit_left_entry",           5),
            ("Right:",          "edit_right_entry",          5),
            ("Top:",            "edit_top_entry",            5),
            ("Bottom:",         "edit_bottom_entry",         5),
            ("Weight:",         "edit_weight_entry",         5),
            ("Edge Threshold:", "edit_edge_threshold_entry", 5),
        ]
        for i, (lbl, attr, w) in enumerate(_simple):
            tk.Label(ef, text=lbl).grid(row=i, column=0, sticky=tk.W)
            entry = tk.Entry(ef, **({"width": w} if w else {}))
            entry.grid(row=i, column=1, sticky=tk.EW)
            setattr(self, attr, entry)
        r = len(_simple)

        off = ttk.Frame(ef)
        off.grid(row=r, column=0, columnspan=2, sticky=tk.EW)
        tk.Label(off, text="Offset X:").pack(side=tk.LEFT)
        self.edit_offset_x = tk.Entry(off, width=4)
        self.edit_offset_x.pack(side=tk.LEFT)
        tk.Label(off, text="Y:").pack(side=tk.LEFT)
        self.edit_offset_y = tk.Entry(off, width=4)
        self.edit_offset_y.pack(side=tk.LEFT)
        r += 1

        tk.Label(ef, text="Rotation:").grid(row=r, column=0, sticky=tk.W)
        self.edit_rotation_entry = tk.Entry(ef)
        self.edit_rotation_entry.grid(row=r, column=1, sticky=tk.EW)
        r += 1

        ttk.Checkbutton(ef, text="Walkable", variable=self.edit_walkable_var).grid(
            row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Checkbutton(ef, text="Avoid Right Edge", variable=self.edit_avoid_right_var).grid(
            row=r, column=0, sticky=tk.W)
        ttk.Checkbutton(ef, text="Avoid Left Edge", variable=self.edit_avoid_left_var).grid(
            row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Checkbutton(ef, text="No Jump from Endpoints", variable=self.edit_no_jump_var).grid(
            row=r, column=0, columnspan=2, sticky=tk.W)

        # Update / Delete buttons
        bf = ttk.Frame(t)
        bf.grid(row=2, column=0, sticky=tk.EW, pady=(4, 2))
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)
        tk.Button(
            bf, text="Update Feature",
            command=lambda: self.master.master.editor.update_feature(self),
        ).grid(row=0, column=0, sticky=tk.EW, padx=(0, 2))
        tk.Button(
            bf, text="Delete Feature",
            command=lambda: self.master.master.editor.delete_feature(self),
        ).grid(row=0, column=1, sticky=tk.EW)

    def _build_portals_tab(self):
        t = self._portals_tab
        pf = ttk.LabelFrame(t, text="Add Portal", padding=4)
        pf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        tk.Label(pf, text="Source (x, y):").grid(row=0, column=0, sticky=tk.W)
        self.portal_src_x = tk.Entry(pf, width=5)
        self.portal_src_x.grid(row=0, column=1)
        self.portal_src_y = tk.Entry(pf, width=5)
        self.portal_src_y.grid(row=0, column=2)
        tk.Label(pf, text="Target (x, y):").grid(row=1, column=0, sticky=tk.W)
        self.portal_tgt_x = tk.Entry(pf, width=5)
        self.portal_tgt_x.grid(row=1, column=1)
        self.portal_tgt_y = tk.Entry(pf, width=5)
        self.portal_tgt_y.grid(row=1, column=2)
        ttk.Checkbutton(pf, text="Bidirectional", variable=self.portal_bidir_var).grid(
            row=2, column=0, columnspan=3, sticky=tk.W)
        tk.Button(
            pf, text="Add Portal",
            command=lambda: self.master.master.editor.register_portal(self),
        ).grid(row=3, column=0, columnspan=3, sticky=tk.EW)

    # ------------------------------------------------------------------
    # create_widgets  (top-level layout within self)
    # ------------------------------------------------------------------

    def create_widgets(self):
        self.columnconfigure(0, weight=1)
        row = 0
        self.return_focus_cb.grid(row=row, column=0, columnspan=2, sticky=tk.W)
        row += 1
        self.bg_black_rb.grid(row=row, column=0, sticky=tk.W)
        self.bg_screenshot_rb.grid(row=row, column=1, sticky=tk.W)
        row += 1
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        row += 1
        self.notebook.grid(row=row, column=0, columnspan=2, sticky=tk.NSEW)
        self.rowconfigure(row, weight=1)
        row += 1
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        row += 1
        self.save_button.grid(row=row, column=0, columnspan=2, sticky=tk.EW)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_bg_change(self):
        self.master.master.editor.set_background_mode(self.bg_var.get())

    def update_selection_label(self, start: str, end: str):
        self.sel_label.config(text=f"Start: {start}   End: {end}")

    def refresh_feature_list(self, names: list[str]):
        self.feature_listbox.delete(0, tk.END)
        for name in names:
            self.feature_listbox.insert(tk.END, name)


# ---------------------------------------------------------------------------
# Pathfinding mode
# ---------------------------------------------------------------------------

class PathfindingFrame(_ModeDependentFrame):
    def __init__(
        self,
        parent: ControlsFrame,
        path_handler,
        on_send_actions: callable,
        **kwargs,
    ):
        super().__init__(parent)

        self.start_pos_label = tk.Label(self, text="Start Position: (0, 0)")
        self.end_pos_label = tk.Label(self, text="End Position: (0, 0)")

        self.allow_teleport_var = tk.BooleanVar(value=True)
        self.allow_teleport_cb = ttk.Checkbutton(
            self, text="Allow Teleport", variable=self.allow_teleport_var
        )
        self.include_portals_var = tk.BooleanVar(value=True)
        self.include_portals_cb = ttk.Checkbutton(
            self, text="Include Portals", variable=self.include_portals_var
        )

        self.speed_multiplier_label = tk.Label(self, text="Speed Multiplier:")
        self.speed_multiplier_entry = tk.Entry(self)
        self.speed_multiplier_entry.insert(0, "1.00")

        self.jump_multiplier_label = tk.Label(self, text="Jump Multiplier:")
        self.jump_multiplier_entry = tk.Entry(self)
        self.jump_multiplier_entry.insert(0, "1.00")

        self.path_handler = path_handler
        modified = self.path_handler.minimap.modified_minimap.copy()
        modified[modified.nonzero()] = 255
        self.master.master.canvas.refresh_canvas(modified)

        self.print_path_var = tk.BooleanVar(value=False)
        self.print_path_cb = ttk.Checkbutton(
            self, text="Print Path", variable=self.print_path_var
        )
        self.print_movements_var = tk.BooleanVar(value=False)
        self.print_movements_cb = ttk.Checkbutton(
            self, text="Print Movements", variable=self.print_movements_var
        )
        self.print_actions_var = tk.BooleanVar(value=False)
        self.print_actions_cb = ttk.Checkbutton(
            self, text="Print Actions", variable=self.print_actions_var
        )
        self.send_actions_button = tk.Button(
            self, text="Get to target", command=on_send_actions
        )

    def create_widgets(self):
        self.start_pos_label.grid(row=0, column=0, sticky=tk.W)
        self.end_pos_label.grid(row=1, column=0, sticky=tk.W)
        self.allow_teleport_cb.grid(row=2, column=0, sticky=tk.W)
        self.include_portals_cb.grid(row=3, column=0, sticky=tk.W)
        self.speed_multiplier_label.grid(row=4, column=0, sticky=tk.W)
        self.speed_multiplier_entry.grid(row=4, column=1, sticky=tk.W)
        self.jump_multiplier_label.grid(row=5, column=0, sticky=tk.W)
        self.jump_multiplier_entry.grid(row=5, column=1, sticky=tk.W)
        self.print_path_cb.grid(row=6, column=0, sticky=tk.W)
        self.print_movements_cb.grid(row=7, column=0, sticky=tk.W)
        self.print_actions_cb.grid(row=8, column=0, sticky=tk.W)
        self.send_actions_button.grid(row=9, column=0, columnspan=2, sticky=tk.EW)

    @property
    def print_path(self) -> bool:
        return self.print_path_var.get()

    @property
    def print_movements(self) -> bool:
        return self.print_movements_var.get()

    @property
    def print_actions(self) -> bool:
        return self.print_actions_var.get()

    def update_start_pos_label(self, x, y):
        self.start_pos_label.config(text=f"Start Position: ({x:.0f}, {y:.0f})")
        self.master.master.editor.update_start_point(int(x), int(y))

    def update_end_pos_label(self, x, y):
        self.end_pos_label.config(text=f"End Position: ({x:.0f}, {y:.0f})")
        self.master.master.editor.update_end_point(int(x), int(y))

    def get_grid_kwargs(self) -> dict:
        try:
            speed_multiplier = float(self.speed_multiplier_entry.get())
            if not (1.00 <= speed_multiplier <= 2.00):
                raise ValueError
        except ValueError:
            speed_multiplier = 1.00

        try:
            jump_multiplier = float(self.jump_multiplier_entry.get())
            if not (1.00 <= jump_multiplier <= 2.00):
                raise ValueError
        except ValueError:
            jump_multiplier = 1.00

        return dict(
            allow_teleport=self.allow_teleport_var.get(),
            speed_multiplier=speed_multiplier,
            jump_multiplier=jump_multiplier,
            include_portals=self.include_portals_var.get(),
        )
