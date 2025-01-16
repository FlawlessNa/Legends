"""
This script handles the Controller, which relays the GUI and the Model together.
"""
import numpy as np
import tkinter as tk
from dataclasses import asdict

from royals.model.mechanics.maple_map import MapleMinimap
from .minimap_edits_model import MinimapEditsManager, MinimapEdits
from .minimap_edits_view import EditorView, FeatureSelectionFrame, PathfindingFrame
from ..movement_mechanics_v2 import MovementHandler


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
        minimap: MapleMinimap,
        edits: MinimapEditsManager = None,
        include_character_position: bool = True,
        ign: str = None,
        scale: int = 5
    ):
        self.minimap = minimap
        self.raw_minimap = self.minimap.parser.get_raw_minimap_grid(binary_mode=True)
        self.edits = edits or MinimapEditsManager()
        self.scale = scale
        self.ign = ign
        self.modified_minimap = self.edits.apply_grid_edits(
            self.raw_minimap, apply_weights=False
        )
        try:
            from royals import royals_ign_finder
            from botting.utilities import client_handler
            self.handle = client_handler.get_client_handle(self.ign, royals_ign_finder)
        except ValueError:
            self.handle = 0

        self.movement_handler = MovementHandler(self.handle, self.minimap)
        self.root = tk.Tk()
        self.view = EditorView(
            self,
            self.modified_minimap,
            self.register_feature,
            self.save_edits,
            self.movement_handler,
            scale
        )
        # Draw each pixel as a larger rectangle and bounding boxes on the existing edits
        self.rectangles = {}
        self.refresh_canvas(self.modified_minimap)
        self.refresh_mode_specific_frame()

        self.character_marker = None
        self.update_char_pos = include_character_position
        self.start_point = self.end_point = None
        self.previous_path = []
        if include_character_position:
            self._map_area_box = self.minimap.get_map_area_box(self.handle)
            self.update_character_position()
            self.root.after(100, self.update_character_position)

        self.root.mainloop()

    def save_edits(self) -> None:
        self.edits.to_json(self.minimap.map_name)

    def refresh_canvas(self, modified_minimap: np.ndarray) -> None:
        self.view.canvas.delete('all')
        self.view.canvas.refresh_canvas(modified_minimap)
        self.draw_rectangles_from_features()

    def refresh_mode_specific_frame(self) -> None:
        if self.view.get_current_mode() == 'Feature Selection':
            sub: FeatureSelectionFrame = self.view.controls_frame.mode_specific_subframe
            sub.update_feature_dropdown(self.edits.names)
            sub.feature_dropdown.bind('<<ComboboxSelected>>', self.update_feature_data)
        else:
            raise NotImplementedError

    def update_feature_data(self, event) -> None:
        assert self.view.get_current_mode() == 'Feature Selection'
        sub: FeatureSelectionFrame = self.view.controls_frame.mode_specific_subframe
        feature_name = sub.feature_dropdown.get()
        self.refresh_canvas(self.modified_minimap)
        sub.reset_entries()
        if feature_name in self.rectangles:
            self.draw_rectangle_in_construction(feature_name)
            feature = next(f for f in self.edits.features if f.name == feature_name)
            sub.update_entries(**asdict(feature))
        self.character_marker = None

    def register_feature(self, frame: FeatureSelectionFrame) -> None:
        try:
            assert self.view.get_current_mode() == 'Feature Selection'
            feature_data = self.get_feature_data(frame)
            assert feature_data['name'] not in ['', None], "Invalid feature name"
            feature = MinimapEdits(**feature_data)
            if feature.name in self.edits.names:
                idx = self.edits.names.index(feature.name)
                self.edits.features[idx] = feature
            else:
                self.edits.features.append(feature)
            print(f"Feature saved: {feature}")
            self.modified_minimap = self.edits.apply_grid_edits(
                self.raw_minimap, apply_weights=False
            )
            self.refresh_canvas(self.modified_minimap)
            self.refresh_mode_specific_frame()
            frame.feature_dropdown.set(feature.name)
            self.draw_rectangle_in_construction(feature.name)
            self.character_marker = None

        except BaseException as e:
            print(f"Error saving feature: {e}")

    def draw_rectangle_in_construction(self, name: str):
        self.view.canvas.delete(self.rectangles[name])
        feature = next(f for f in self.edits.features if f.name == name)
        self.rectangles[name] = self.view.canvas.create_rectangle(
            feature.left * self.scale,
            feature.top * self.scale,
            feature.right * self.scale,
            feature.bottom * self.scale,
            outline='orange'
        )

    @staticmethod
    def get_feature_data(frame: FeatureSelectionFrame) -> dict:
        return {
            'name': frame.name_entry.get(),
            'left': int(frame.left_entry.get()),
            'right': int(frame.right_entry.get()),
            'top': int(frame.top_entry.get()),
            'bottom': int(frame.bottom_entry.get()),
            'offset': (
                int(frame.offset_x_entry.get() or 0),
                int(frame.offset_y_entry.get() or 0)
            ),
            'weight': int(frame.weight_entry.get() or 1),
            'walkable': frame.walkable_var.get(),
            'rotation_indexes': [
                int(i.strip()) for i in frame.rotation_entry.get().split(',') if i
            ],
            'avoid_right_edge': frame.avoid_right_edge_var.get(),
            'avoid_left_edge': frame.avoid_left_edge_var.get(),
            'edge_threshold': int(frame.edge_threshold_entry.get() or 5),
            'no_jump_connections_from_endpoints': frame.no_jump_connections_var.get(),
        }

    def update_character_position(self):
        pos = self.minimap.get_character_positions(
            self.handle, map_area_box=self._map_area_box
        ).pop()
        coords = (
            pos[0] * self.scale,
            pos[1] * self.scale,
            (pos[0] + 1) * self.scale,
            (pos[1] + 1) * self.scale
        )

        # If the character position marker exists, update its position
        if self.character_marker is None:
            self.character_marker = self.view.canvas.create_rectangle(
                *coords, fill='yellow'
            )
        else:
            self.view.canvas.coords(self.character_marker, *coords)

        self.root.after(100, self.update_character_position)

    def draw_rectangles_from_features(self):
        self.delete_rectangles()
        for feature in self.edits.features:
            left = feature.left
            right = feature.right
            top = feature.top
            bottom = feature.bottom
            self.rectangles[feature.name] = self.view.canvas.create_rectangle(
                left * self.scale,
                top * self.scale,
                right * self.scale,
                bottom * self.scale,
                outline='green'
            )

    def delete_rectangles(self):
        for rect in self.rectangles.values():
            self.view.canvas.delete(rect)
        self.rectangles = {}

    def update_start_point(self, x, y) -> None:
        self.start_point = (x, y)
        self.calculate_and_display_path()

    def update_end_point(self, x, y) -> None:
        self.end_point = (x, y)
        self.calculate_and_display_path()

    def calculate_and_display_path(self) -> None:
        if self.start_point is not None and self.end_point is not None:
            frame: PathfindingFrame = self.view.controls_frame.mode_specific_subframe
            assert isinstance(frame, PathfindingFrame)
            kwargs = frame.get_grid_kwargs()

            for node in self.previous_path:
                if (node.x, node.y) in {self.start_point, self.end_point}:
                    continue
                self.view.canvas.draw_point(node.x, node.y, 'white')

            grid = self.minimap.generate_grid(**kwargs)
            path = self.movement_handler.compute_path(
                self.start_point, self.end_point, grid
            )
            movements = self.movement_handler.path_into_movements(path, grid)
            actions = self.movement_handler.movements_into_action(movements, grid)
            if frame.print_path:
                print(f"Path: \n{'\n'.join(map(str, path))}")  # noqa
            if frame.print_movements:
                print(f"Movements: \n{'\n'.join(map(str, movements))}")
            if frame.print_actions:
                print(f"Actions: \n {actions}")
            for node in path:
                if (node.x, node.y) in {self.start_point, self.end_point}:
                    continue
                self.view.canvas.draw_point(node.x, node.y, 'green')

            self.previous_path = path