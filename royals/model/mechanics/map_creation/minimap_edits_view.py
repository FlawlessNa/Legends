"""
GUI/View class & components for the Editor.
"""

from abc import ABC, abstractmethod
from PIL import Image, ImageTk
import cv2
import numpy as np
import tkinter as tk
import tkinter.ttk as ttk


class EditorView(ttk.Frame):
    def __init__(
        self,
        editor,
        edited_minimap: np.ndarray,
        register: callable,
        save: callable,
        path_handler: ...,
        scale: int = 5,
        *args,
        **kwargs,
    ):
        self.editor = editor
        self.editor.root.title("Minimap Editor")
        super().__init__(self.editor.root)
        self.pack(fill=tk.BOTH, expand=True)

        self.controls_frame = ControlsFrame(self, register, save, path_handler)
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

    def update_box_entries(self, x1, y1, x2, y2):
        assert (
            self.get_current_mode() == "Feature Selection"
        ), f"Cannot update Box entries under mode {self.get_current_mode()}"
        left = int(min(x1, x2))
        right = int(max(x1, x2))
        top = int(min(y1, y2))
        bottom = int(max(y1, y2))
        subframe: FeatureSelectionFrame = (
            self.controls_frame.mode_specific_subframe
        )  # noqa
        subframe.left_entry.delete(0, tk.END)
        subframe.left_entry.insert(0, str(left))

        subframe.right_entry.delete(0, tk.END)
        subframe.right_entry.insert(0, str(right))

        subframe.top_entry.delete(0, tk.END)
        subframe.top_entry.insert(0, str(top))

        subframe.bottom_entry.delete(0, tk.END)
        subframe.bottom_entry.insert(0, str(bottom))

    def draw_temp_rectangle(self, x1, y1, x2, y2) -> None:
        return self.canvas.draw_temp_rectangle(x1, y1, x2, y2)


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

        self.start_x = self.start_y = self.temp_rect = self.image_displayed = None
        self.start_point = self.end_point = None
        self.start_point_id = self.end_point_id = None

    def get_current_mode(self) -> str:
        return self.master.get_current_mode()

    def get_cursor_pos(self, event):
        return self.canvasx(event.x) // self.scale, self.canvasy(event.y) // self.scale

    def refresh_canvas(self, img: np.ndarray) -> None:
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        scaled = pil_img.resize(
            (img.shape[1] * self.scale, img.shape[0] * self.scale),
            Image.NEAREST,  # noqa
        )
        self.image_displayed = ImageTk.PhotoImage(scaled)
        self.create_image(0, 0, image=self.image_displayed, anchor=tk.NW)

    def draw_temp_rectangle(self, x1, y1, x2, y2) -> None:
        if self.temp_rect is not None:
            self.delete(self.temp_rect)
        scale = self.scale
        self.temp_rect = self.create_rectangle(
            x1 * scale, y1 * scale, x2 * scale, y2 * scale, outline="red"
        )

    def draw_point(self, x, y, color):
        min_x = x * self.scale
        min_y = y * self.scale
        max_x = (x + 1) * self.scale
        max_y = (y + 1) * self.scale
        return self.create_rectangle(
            min_x,
            min_y,
            max_x,
            max_y,
            fill=color,
            outline=color,
        )

    def on_button_press(self, event):
        if self.get_current_mode() == "Feature Selection":
            self.start_x, self.start_y = self.get_cursor_pos(event)
            self.draw_temp_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y
            )
        elif self.get_current_mode() == "Pathfinding Exploration":
            x, y = self.get_cursor_pos(event)
            if event.state & 0x0004:  # Check if Ctrl key is pressed
                if self.end_point_id is not None:
                    self.delete(self.end_point_id)
                self.end_point = (x, y)
                self.end_point_id = self.draw_point(x, y, "blue")
                self.master.controls_frame.mode_specific_subframe.update_end_pos_label(
                    x, y
                )
            else:
                if self.start_point_id is not None:
                    self.delete(self.start_point_id)
                self.start_point = (x, y)
                self.start_point_id = self.draw_point(x, y, "red")
                self.master.controls_frame.mode_specific_subframe.update_start_pos_label(
                    x, y
                )

    def on_mouse_drag(self, event):
        self.on_mouse_move(event)
        cur_x, cur_y = self.get_cursor_pos(event)
        if self.get_current_mode() == "Feature Selection":
            self.draw_temp_rectangle(self.start_x, self.start_y, cur_x, cur_y)
            self.master.update_box_entries(self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        if self.get_current_mode() == "Feature Selection":
            end_x, end_y = self.get_cursor_pos(event)
            self.draw_temp_rectangle(self.start_x, self.start_y, end_x, end_y)
            self.master.update_box_entries(self.start_x, self.start_y, end_x, end_y)

    def on_mouse_move(self, event):
        cur_x = self.canvasx(event.x) // self.scale
        cur_y = self.canvasy(event.y) // self.scale
        self.master.coord_label.config(text=f"Coordinates: ({cur_x:.0f}, {cur_y:.0f})")

    def on_key_press(self, event):
        if self.get_current_mode() == "Pathfinding Exploration":
            if event.keysym in ["Left", "Right", "Up", "Down"]:
                if event.state & 0x0004:  # Check if Ctrl key is pressed
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
        if direction == "Left":
            x -= 1
        elif direction == "Right":
            x += 1
        elif direction == "Up":
            y -= 1
        elif direction == "Down":
            y += 1
        self.delete(point_id)
        if point_type == "start":
            self.start_point = (x, y)
            self.start_point_id = self.draw_point(x, y, color)
            self.master.controls_frame.mode_specific_subframe.update_start_pos_label(
                x, y
            )
        else:
            self.end_point = (x, y)
            self.end_point_id = self.draw_point(x, y, color)
            self.master.controls_frame.mode_specific_subframe.update_end_pos_label(x, y)


class ControlsFrame(ttk.Frame):
    master: EditorView

    def __init__(
        self, parent, feature_saver: callable, edits_saver: callable, path_handler: ...
    ):
        super().__init__(parent)
        self.feature_saver = feature_saver
        self.edits_saver = edits_saver
        self.path_handler = path_handler
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
            "Feature Selection": FeatureSelectionFrame,
            "Pathfinding Exploration": PathfindingFrame,
        }[curr_mode]

        self.mode_specific_subframe: _ModeDependentFrame = mode_class(
            self,
            register_procedure=self.feature_saver,
            save_edits=self.edits_saver,
            path_handler=self.path_handler,
        )
        self.mode_specific_subframe.create_widgets()

    def draw_temp_rectangle(self, x1, y1, x2, y2):
        self.master.draw_temp_rectangle(x1, y1, x2, y2)


class _ModeSelectionSubFrame(ttk.Frame):
    master: ControlsFrame
    _MODES = ["Feature Selection", "Pathfinding Exploration"]

    def __init__(self, parent: ControlsFrame):
        super().__init__(parent)
        self.pack(side=tk.TOP, anchor=tk.W)

        # Variable to store the selected mode
        self.current_mode = tk.StringVar(value=self._MODES[0])

        # Create a frame to select between modes
        ttk.Label(self, text="Select Mode:").pack(side=tk.TOP, anchor=tk.W)
        for mode in self._MODES:
            rb = tk.Radiobutton(
                self,
                text=mode,
                variable=self.current_mode,
                value=mode,
                command=self.on_mode_change,
            )
            rb.pack(anchor=tk.W)

    def on_mode_change(self):
        print(f"Mode changed to: {self.current_mode.get()}")
        self.master.update_mode_dependent_frame(self.current_mode.get())


class _ModeDependentFrame(ttk.Frame, ABC):
    master: ControlsFrame

    def __init__(self, parent: ControlsFrame, **kwargs):
        super().__init__(parent)
        self.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    @abstractmethod
    def create_widgets(self):
        pass


class FeatureSelectionFrame(_ModeDependentFrame):
    def __init__(
        self,
        parent: ControlsFrame,
        register_procedure: callable,
        save_edits: callable,
        **kwargs,
    ):
        super().__init__(parent)
        self.feature_selector = tk.StringVar(value="<new>")
        self.dropdown_label = tk.Label(self, text="Select Feature:")
        self.feature_dropdown = ttk.Combobox(self, textvariable=self.feature_selector)

        # Inputs
        self.name_label = tk.Label(self, text="Feature Name:")
        self.name_entry = tk.Entry(self)

        self.left_label = tk.Label(self, text="Left:")
        self.left_entry = tk.Entry(self, width=5)

        self.right_label = tk.Label(self, text="Right:")
        self.right_entry = tk.Entry(self, width=5)

        self.top_label = tk.Label(self, text="Top:")
        self.top_entry = tk.Entry(self, width=5)

        self.bottom_label = tk.Label(self, text="Bottom:")
        self.bottom_entry = tk.Entry(self, width=5)

        self.offset_frame = ttk.Frame(self)
        self.offset_label = tk.Label(self.offset_frame, text="Offset Nodes by:")
        self.offset_label.pack(side=tk.LEFT)
        self.offset_x_label = tk.Label(self.offset_frame, text="X:")
        self.offset_x_entry = tk.Entry(self.offset_frame, width=5)
        self.offset_y_entry = tk.Entry(self.offset_frame, width=5)
        self.offset_y_label = tk.Label(self.offset_frame, text="Y:")
        self.offset_y_entry.pack(side=tk.RIGHT)
        self.offset_y_label.pack(side=tk.RIGHT)
        self.offset_x_entry.pack(side=tk.RIGHT)
        self.offset_x_label.pack(side=tk.RIGHT)

        self.weight_label = tk.Label(self, text="Weight:")
        self.weight_entry = tk.Entry(self, width=5)

        self.rotation_label = tk.Label(self, text="Rotation Indexes:")
        self.rotation_entry = tk.Entry(self, width=15)

        self.walkable_var = tk.BooleanVar(value=True)
        self.walkable_cb = ttk.Checkbutton(
            self, text="Walkable", variable=self.walkable_var
        )

        self.avoid_right_edge_var = tk.BooleanVar(value=True)
        self.avoid_left_edge_var = tk.BooleanVar(value=True)
        self.avoid_right_edge_cb = ttk.Checkbutton(
            self, text="Avoid Right Edge", variable=self.avoid_right_edge_var
        )
        self.avoid_left_edge_cb = ttk.Checkbutton(
            self, text="Avoid Left Edge", variable=self.avoid_left_edge_var
        )
        self.edge_threshold_label = tk.Label(self, text="Edge Threshold:")
        self.edge_threshold_entry = tk.Entry(self, width=5)

        self.no_jump_connections_var = tk.BooleanVar(value=False)
        self.no_jump_connections_cb = ttk.Checkbutton(
            self,
            text="No Jump Connections from Endpoints",
            variable=self.no_jump_connections_var,
        )
        self.register_button = tk.Button(
            self, text="Register Feature", command=lambda: register_procedure(self)
        )
        self.save_button = tk.Button(self, text="Save Edits", command=save_edits)

    def create_widgets(self):
        self.dropdown_label.grid(row=0, column=0, sticky=tk.W)
        self.feature_dropdown.grid(row=0, column=1, sticky=tk.EW)
        self.feature_dropdown.set("<new>")

        self.name_label.grid(row=1, column=0, sticky=tk.W)
        self.name_entry.grid(row=1, column=1, sticky=tk.EW)

        self.left_label.grid(row=2, column=0, sticky=tk.W)
        self.left_entry.grid(row=2, column=1, sticky=tk.W)
        self.left_entry.bind("<KeyRelease>", self.on_coord_entry_change)

        self.right_label.grid(row=3, column=0, sticky=tk.W)
        self.right_entry.grid(row=3, column=1, sticky=tk.W)
        self.right_entry.bind("<KeyRelease>", self.on_coord_entry_change)

        self.top_label.grid(row=4, column=0, sticky=tk.W)
        self.top_entry.grid(row=4, column=1, sticky=tk.W)
        self.top_entry.bind("<KeyRelease>", self.on_coord_entry_change)

        self.bottom_label.grid(row=5, column=0, sticky=tk.W)
        self.bottom_entry.grid(row=5, column=1, sticky=tk.W)
        self.bottom_entry.bind("<KeyRelease>", self.on_coord_entry_change)

        self.weight_label.grid(row=6, column=0, sticky=tk.W)
        self.weight_entry.grid(row=6, column=1, sticky=tk.W)

        self.rotation_label.grid(row=7, column=0, sticky=tk.W)
        self.rotation_entry.grid(row=7, column=1, sticky=tk.W)

        self.offset_frame.grid(row=8, column=0, columnspan=2, sticky=tk.EW)

        self.avoid_right_edge_cb.grid(row=9, column=0, sticky=tk.W)
        self.avoid_left_edge_cb.grid(row=9, column=1, sticky=tk.W)
        self.edge_threshold_label.grid(row=10, column=0, sticky=tk.W)
        self.edge_threshold_entry.grid(row=10, column=1, sticky=tk.W)

        self.walkable_cb.grid(row=11, column=0, sticky=tk.W)

        self.no_jump_connections_cb.grid(row=12, column=0, columnspan=2, sticky=tk.W)

        self.register_button.grid(row=13, column=0, columnspan=2, sticky=tk.EW)
        self.save_button.grid(row=14, column=0, columnspan=2, sticky=tk.EW)

    def update_feature_dropdown(self, names: list[str]):
        self.feature_dropdown["values"] = ["<new>"] + names

    def on_coord_entry_change(self, event):
        try:
            left = int(self.left_entry.get())
            right = int(self.right_entry.get())
            top = int(self.top_entry.get())
            bottom = int(self.bottom_entry.get())
            self.master.draw_temp_rectangle(left, top, right, bottom)
        except BaseException as e:
            print(e)
            pass

    def update_entries(
        self,
        *,
        left: int,
        right: int,
        top: int,
        bottom: int,
        name: str,
        offset: tuple[int, int],
        walkable: bool,
        weight: int,
        avoid_right_edge: bool,
        avoid_left_edge: bool,
        edge_threshold: int,
        no_jump_connections_from_endpoints: bool,
        rotation_indexes: list[int],
        **kwargs,
    ):
        self.name_entry.insert(0, name)
        self.left_entry.insert(0, str(left))
        self.right_entry.insert(0, str(right))
        self.top_entry.insert(0, str(top))
        self.bottom_entry.insert(0, str(bottom))
        self.offset_x_entry.insert(0, str(offset[0]))
        self.offset_y_entry.insert(0, str(offset[1]))
        self.walkable_var.set(walkable)
        self.weight_entry.insert(0, str(weight))
        self.avoid_right_edge_var.set(avoid_right_edge)
        self.avoid_left_edge_var.set(avoid_left_edge)
        self.edge_threshold_entry.insert(0, str(edge_threshold))
        self.no_jump_connections_var.set(no_jump_connections_from_endpoints)
        self.rotation_entry.insert(0, ", ".join(map(str, rotation_indexes)))

    def reset_entries(self):
        self.name_entry.delete(0, tk.END)
        self.left_entry.delete(0, tk.END)
        self.right_entry.delete(0, tk.END)
        self.top_entry.delete(0, tk.END)
        self.bottom_entry.delete(0, tk.END)
        self.offset_x_entry.delete(0, tk.END)
        self.offset_y_entry.delete(0, tk.END)
        self.weight_entry.delete(0, tk.END)
        self.rotation_entry.delete(0, tk.END)
        self.walkable_var.set(True)
        self.avoid_right_edge_var.set(True)
        self.avoid_left_edge_var.set(True)
        self.edge_threshold_entry.delete(0, tk.END)
        self.no_jump_connections_var.set(False)


class PathfindingFrame(_ModeDependentFrame):
    def __init__(self, parent: ControlsFrame, path_handler: ..., **kwargs):
        super().__init__(parent)
        self.path_handler = path_handler

        self.start_pos_label = tk.Label(self, text="Start Position: (0, 0)")
        self.end_pos_label = tk.Label(self, text="End Position: (0, 0)")

        self.allow_teleport_var = tk.BooleanVar(value=True)
        self.allow_teleport_cb = ttk.Checkbutton(
            self,
            text="Allow Teleport",
            variable=self.allow_teleport_var,
            command=self.on_allow_teleport_toggle,
        )
        self.include_portals_var = tk.BooleanVar(value=True)
        self.include_portals_cb = ttk.Checkbutton(
            self,
            text="Include Portals",
            variable=self.include_portals_var,
            command=self.on_include_portals_toggle,
        )
        self.speed_multiplier_label = tk.Label(self, text="Speed Multiplier:")
        self.speed_multiplier_entry = tk.Entry(self)
        self.speed_multiplier_entry.insert(0, "1.00")

        self.jump_multiplier_label = tk.Label(self, text="Jump Multiplier:")
        self.jump_multiplier_entry = tk.Entry(self)
        self.jump_multiplier_entry.insert(0, "1.00")

    def create_widgets(self):
        self.start_pos_label.grid(row=0, column=0, sticky=tk.W)
        self.end_pos_label.grid(row=1, column=0, sticky=tk.W)
        self.allow_teleport_cb.grid(row=2, column=0, sticky=tk.W)
        self.include_portals_cb.grid(row=3, column=0, sticky=tk.W)
        self.speed_multiplier_label.grid(row=4, column=0, sticky=tk.W)
        self.speed_multiplier_entry.grid(row=4, column=1, sticky=tk.W)
        self.jump_multiplier_label.grid(row=5, column=0, sticky=tk.W)
        self.jump_multiplier_entry.grid(row=5, column=1, sticky=tk.W)

    def update_start_pos_label(self, x, y):
        self.start_pos_label.config(text=f"Start Position: ({x:.0f}, {y:.0f})")
        self.master.master.editor.update_start_point(int(x), int(y))

    def update_end_pos_label(self, x, y):
        self.end_pos_label.config(text=f"End Position: ({x:.0f}, {y:.0f})")
        self.master.master.editor.update_end_point(int(x), int(y))

    def on_allow_teleport_toggle(self):
        if self.allow_teleport_var.get():
            print("Option 1 toggled on")

    def on_include_portals_toggle(self):
        if self.include_portals_var.get():
            print("Option 2 toggled on")

    def get_grid_kwargs(self) -> dict:
        try:
            speed_multiplier = float(self.speed_multiplier_entry.get())
            if not (1.00 <= speed_multiplier <= 2.00):
                raise ValueError("Speed multiplier must be between 1.00 and 2.00")
        except ValueError:
            speed_multiplier = 1.00

        try:
            jump_multiplier = float(self.jump_multiplier_entry.get())
            if not (1.00 <= jump_multiplier <= 2.00):
                raise ValueError("Jump multiplier must be between 1.00 and 2.00")
        except ValueError:
            jump_multiplier = 1.00

        return dict(
            allow_teleport=self.allow_teleport_var.get(),
            speed_multiplier=speed_multiplier,
            jump_multiplier=jump_multiplier,
            include_portals=self.include_portals_var.get(),
        )
