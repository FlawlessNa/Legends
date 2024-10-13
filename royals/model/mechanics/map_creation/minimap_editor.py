import cv2
from abc import ABC, abstractmethod
import numpy as np
import tkinter.ttk as ttk
import tkinter as tk
from PIL import Image, ImageTk
from .minimap_edits import MinimapEditsManager, MinimapEdits
from royals.model.interface import Minimap
from royals import royals_ign_finder
from botting.utilities import client_handler

IGN = 'StarBase'


class ModeFrame(ttk.Frame, ABC):
    def __init__(self, parent, editor: "MinimapEditor"):
        super().__init__(parent)
        self.editor = editor

    @abstractmethod
    def create_widgets(self):
        pass


class FeatureSelectionFrame(ModeFrame):
    def __init__(self, parent, editor: "MinimapEditor"):
        super().__init__(parent, editor)
        feature_selector = tk.StringVar(value='<new>')
        self.dropdown_label = tk.Label(self, text='Select Feature:')
        self.feature_dropdown = ttk.Combobox(self, textvariable=feature_selector)

        # Inputs
        self.name_label = tk.Label(self, text='Feature Name:')
        self.name_entry = tk.Entry(self)

        self.left_label = tk.Label(self, text='Left:')
        self.left_entry = tk.Entry(self, width=5)

        self.right_label = tk.Label(self, text='Right:')
        self.right_entry = tk.Entry(self, width=5)

        self.top_label = tk.Label(self, text='Top:')
        self.top_entry = tk.Entry(self, width=5)

        self.bottom_label = tk.Label(self, text='Bottom:')
        self.bottom_entry = tk.Entry(self, width=5)

        self.offset_frame = ttk.Frame(self)
        self.offset_label = tk.Label(self.offset_frame, text='Offset Nodes by:')
        self.offset_label.pack(side=tk.LEFT)
        self.offset_x_label = tk.Label(self.offset_frame, text='X:')
        self.offset_x_entry = tk.Entry(self.offset_frame, width=5)
        self.offset_y_entry = tk.Entry(self.offset_frame, width=5)
        self.offset_y_label = tk.Label(self.offset_frame, text='Y:')
        self.offset_y_entry.pack(side=tk.RIGHT)
        self.offset_y_entry.bind("<KeyRelease>", self.draw_box_from_entries)
        self.offset_y_label.pack(side=tk.RIGHT)
        self.offset_x_entry.pack(side=tk.RIGHT)
        self.offset_x_entry.bind("<KeyRelease>", self.draw_box_from_entries)
        self.offset_x_label.pack(side=tk.RIGHT)

        self.weight_label = tk.Label(self, text='Weight:')
        self.weight_entry = tk.Entry(self, width=5)

    def create_widgets(self):
        self.dropdown_label.grid(row=0, column=0, sticky=tk.W)
        self.feature_dropdown.grid(row=0, column=1, sticky=tk.EW)
        self.update_feature_dropdown()

        self.name_label.grid(row=1, column=0, sticky=tk.W)
        self.name_entry.grid(row=1, column=1, sticky=tk.EW)

        self.left_label.grid(row=2, column=0, sticky=tk.W)
        self.left_entry.grid(row=2, column=1, sticky=tk.W)
        self.left_entry.bind("<KeyRelease>", self.draw_box_from_entries)

        self.right_label.grid(row=3, column=0, sticky=tk.W)
        self.right_entry.grid(row=3, column=1, sticky=tk.W)
        self.right_entry.bind("<KeyRelease>", self.draw_box_from_entries)

        self.top_label.grid(row=4, column=0, sticky=tk.W)
        self.top_entry.grid(row=4, column=1, sticky=tk.W)
        self.top_entry.bind("<KeyRelease>", self.draw_box_from_entries)

        self.bottom_label.grid(row=5, column=0, sticky=tk.W)
        self.bottom_entry.grid(row=5, column=1, sticky=tk.W)
        self.bottom_entry.bind("<KeyRelease>", self.draw_box_from_entries)

        self.weight_label.grid(row=6, column=0, sticky=tk.W)
        self.weight_entry.grid(row=6, column=1, sticky=tk.W)

        self.offset_frame.grid(row=7, column=0, columnspan=2, sticky=tk.EW)

    def update_feature_dropdown(self):
        features = []
        if self.editor.edits is not None:
            features = [f.name for f in self.editor.edits.features]
        self.feature_dropdown['values'] = ['<new>'] + features
        self.feature_dropdown.set('<new>')

    def draw_box_from_entries(self, event):
        print(event)
        left = int(self.left_entry.get())
        right = int(self.right_entry.get())
        top = int(self.top_entry.get())
        bottom = int(self.bottom_entry.get())
        offset_x = int(self.offset_x_entry.get() or 0)
        offset_y = int(self.offset_y_entry.get() or 0)
        try:
            feature = MinimapEdits(
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                offset=(offset_x, offset_y)
            )
            self.editor.current_feature = feature
            if self.editor.rect:
                self.editor.canvas.delete(self.editor.rect)
            self.editor.rect = self.editor.canvas.create_rectangle(
                (left + offset_x) * self.editor.scale,
                (top + offset_y) * self.editor.scale,
                (right + offset_x) * self.editor.scale,
                (bottom + offset_y) * self.editor.scale,
                outline='red', fill='red'
            )
        except AssertionError:
            pass

    def update_entries(self, feature: MinimapEdits):
        self.left_entry.delete(0, tk.END)
        self.left_entry.insert(0, str(feature.left))

        self.right_entry.delete(0, tk.END)
        self.right_entry.insert(0, str(feature.right))

        self.top_entry.delete(0, tk.END)
        self.top_entry.insert(0, str(feature.top))

        self.bottom_entry.delete(0, tk.END)
        self.bottom_entry.insert(0, str(feature.bottom))

        self.offset_x_entry.delete(0, tk.END)
        self.offset_x_entry.insert(0, str(feature.offset[0]))

        self.offset_y_entry.delete(0, tk.END)
        self.offset_y_entry.insert(0, str(feature.offset[1]))


class MinimapEditor:
    """
    This class is used to load a raw minimap canvas from game files, along with any
    existing modifications to the minimap, specified by a MinimapEdits instance.
    It displays a tkinter editor to allow the user to modify the minimap.

    These edits can be saved for future usage, or they can be used directly for the
    current session without saving.
    """
    def __init__(
        self,
        raw_minimap: np.ndarray,
        edits: MinimapEditsManager = None,
        include_character_position: bool = True,
        scale: int = 5
    ):
        self.raw_minimap = self.modified_minimap = raw_minimap
        self.edits = edits
        self.scale = scale
        if self.edits is not None:
            self.modified_minimap = edits.apply_edits(self.raw_minimap)

        self.root = tk.Tk()
        self.root.title("Minimap Editor")

        # Create main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create canvas
        self.canvas = tk.Canvas(
            self.main_frame,
            width=self.modified_minimap.shape[1] * self.scale,
            height=self.modified_minimap.shape[0] * self.scale
        )
        self.canvas.pack(side=tk.LEFT)

        self.selector_frame = ttk.Frame(self.main_frame)
        self.selector_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Create a frame to select between modes
        ttk.Label(self.selector_frame, text="Select Mode:").pack(
            side=tk.TOP, anchor=tk.W
        )
        self.mode_selection_frame = ttk.Frame(self.selector_frame)
        self.mode_selection_frame.pack(side=tk.TOP, anchor=tk.W)

        # The dependent frame will vary based on the selected mode
        self.mode_dependent_frame = ttk.Frame(self.selector_frame)
        self.mode_dependent_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        # Variable to store the selected mode
        self.mode = tk.StringVar(value="Feature Selection")
        self.update_mode_dependent_frame()

        # Add radio buttons for mode selection
        modes = ["Feature Selection", "Edit Individual Nodes", "Explore Trajectories"]
        for mode in modes:
            rb = tk.Radiobutton(
                self.mode_selection_frame,
                text=mode,
                variable=self.mode,
                value=mode,
                command=self.change_mode
            )
            rb.pack(anchor=tk.W)

        # Draw each pixel as a larger rectangle
        self.update_canvas(self.modified_minimap)

        self.start_x = self.start_y = 0
        self.rect = None
        self.box = None

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.canvas.bind("<Motion>", self.on_mouse_move)

        self.coord_label = tk.Label(self.root, text="Coordinates: (0, 0)")
        self.coord_label.pack()

        if include_character_position:
            class FakeMinimap(Minimap):
                def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
                    pass

                map_area_width = self.modified_minimap.shape[1]
                map_area_height = self.modified_minimap.shape[0]


            self.handle = client_handler.get_client_handle(IGN, royals_ign_finder)
            self._mini_pos_retrieve = FakeMinimap()
            self._map_area_box = self._mini_pos_retrieve.get_map_area_box(self.handle)
            self.update_character_position()
            self.root.after(100, self.update_character_position)

        self.root.mainloop()

    def change_mode(self):
        print(f"Mode changed to: {self.mode.get()}")
        self.update_mode_dependent_frame()

    def update_character_position(self):
        pos = self._mini_pos_retrieve.get_character_positions(
            self.handle, map_area_box=self._map_area_box
        ).pop()
        modified_img = self.modified_minimap.copy()
        cv2.circle(modified_img, pos, 1, (0, 255, 255), 1)
        self.update_canvas(modified_img)

        self.root.after(100, self.update_character_position)

    def update_canvas(self, img: np.ndarray):
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        scaled = pil_img.resize(
            (img.shape[1] * self.scale, img.shape[0] * self.scale), Image.NEAREST
        )
        self.tk_img = ImageTk.PhotoImage(scaled)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)

    def update_mode_dependent_frame(self):
        for widget in self.mode_dependent_frame.winfo_children():
            widget.destroy()

        mode_class = {
            "Feature Selection": FeatureSelectionFrame,
            "Edit Individual Nodes": ...,
        }[self.mode.get()]

        frame = mode_class(self.mode_dependent_frame, self)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.create_widgets()
        self.feature_selection_frame = frame

    def save_feature(self):
        print('Saving Feature')
        # feature = MinimapFeature(
        #     avoid_staying_on_edges=self.avoid_staying_on_edges_var.get(),
        #     no_jump_connections_from_endpoints=self.no_jump_connections_var.get()
        # )
        # print(f"Feature saved: {feature}")

    def on_button_press(self, event):
        self.start_x = self.canvas.canvasx(event.x) // self.scale
        self.start_y = self.canvas.canvasy(event.y) // self.scale
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x * self.scale,
            self.start_y * self.scale,
            self.start_x * self.scale,
            self.start_y * self.scale,
            outline='red', fill='red'
        )

    def on_mouse_drag(self, event):
        cur_x = self.canvas.canvasx(event.x) // self.scale
        cur_y = self.canvas.canvasy(event.y) // self.scale
        self.canvas.coords(
            self.rect,
            self.start_x * self.scale,
            self.start_y * self.scale,
            cur_x * self.scale,
            cur_y * self.scale
        )

    def on_button_release(self, event):
        end_x = self.canvas.canvasx(event.x) // self.scale
        end_y = self.canvas.canvasy(event.y) // self.scale
        start_x = int(min(self.start_x, end_x))
        end_x = int(max(self.start_x, end_x))
        start_y = int(min(self.start_y, end_y))
        end_y = int(max(self.start_y, end_y))
        self.current_feature = MinimapEdits(
            left=start_x, right=end_x, top=start_y, bottom=end_y
        )
        print(f"Feature created: {self.current_feature}")

        if self.feature_selection_frame:
            self.feature_selection_frame.update_entries(self.current_feature)

    def on_mouse_move(self, event):
        cur_x = self.canvas.canvasx(event.x) // self.scale
        cur_y = self.canvas.canvasy(event.y) // self.scale
        self.coord_label.config(text=f"Coordinates: ({cur_x}, {cur_y})")
