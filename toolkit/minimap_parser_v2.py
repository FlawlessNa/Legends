"""
Helper script to code new minimap features seamlessly.
These features are transcribed to a file, which can later be fine-tuned as needed.

"""
# According to Copilot:
# x: The x-coordinate of the object in the map.
# y: The y-coordinate of the object in the map.
# z: The z-index of the object, which determines the drawing order (higher values are drawn on top of lower values).
# f: The flip value, which indicates whether the object should be flipped horizontally (1 for flipped, 0 for not flipped).
# zM: The zoom multiplier, which scales the object (1 means no scaling, values greater than 1 scale up, and values less than 1 scale down).
# r: The rotation value, which specifies the rotation angle of the object in degrees.


# TODO - All we need now is to offset the coordinates.
import cv2
import keyboard
import os
import numpy as np
import xml.etree.ElementTree as ElementTree

from paths import ROOT
from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler
from botting.utilities import Box

HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
OUTPUT_LOCATION = os.path.join(ROOT, "royals/model/minimaps/")
OUTPUT_NAME = "test.py"
MAP_FILENAME = "MysteriousPath3.xml"
BRIGHTNESS_THRESH = 10  # After reducing to minimap size, the threshold for binary conversion

tree = ElementTree.parse(
    os.path.join(ROOT, f"royals/assets/game_files/maps/{MAP_FILENAME}")
)
root = tree.getroot()
foothold = root.find(".//imgdir[@name='foothold']")
ropes = root.find(".//imgdir[@name='ladderRope']")
info_section = root.find(".//imgdir[@name='info']")
minimap_section = root.find(".//imgdir[@name='miniMap']")

TELEPORT_DISTANCE = 150
PHYSICS_SPEED = 125
PHYSICS_JUMP_SPEED = 555
PHYSICS_GRAVITY = 2000

VRTop = int(info_section.find("int[@name='VRTop']").attrib["value"])
VRLeft = int(info_section.find("int[@name='VRLeft']").attrib["value"])
VRBottom = int(info_section.find("int[@name='VRBottom']").attrib["value"])
VRRight = int(info_section.find("int[@name='VRRight']").attrib["value"])
VRWidth = VRRight - VRLeft
VRHeight = VRBottom - VRTop

MINIMAP_CANVAS_WIDTH = int(
    minimap_section.find("canvas[@name='canvas']").attrib["width"]
)
MINIMAP_CANVAS_HEIGHT = int(
    minimap_section.find("canvas[@name='canvas']").attrib["height"]
)
MINIMAP_VR_WIDTH = int(minimap_section.find("int[@name='width']").attrib["value"])
MINIMAP_VR_HEIGHT = int(minimap_section.find("int[@name='height']").attrib["value"])
MINIMAP_CENTER_X = int(minimap_section.find("int[@name='centerX']").attrib["value"])
MINIMAP_CENTER_Y = int(minimap_section.find("int[@name='centerY']").attrib["value"])
MINIMAP_SCALE_X = MINIMAP_VR_WIDTH / MINIMAP_CANVAS_WIDTH
MINIMAP_SCALE_Y = MINIMAP_VR_HEIGHT / MINIMAP_CANVAS_HEIGHT


VRJumpHeight = PHYSICS_JUMP_SPEED**2 / (2 * PHYSICS_GRAVITY)
VRJumpDuration = 2 * PHYSICS_JUMP_SPEED / PHYSICS_GRAVITY
VRJumpWidth = VRJumpDuration * PHYSICS_SPEED


def is_vertical(element):
    return element["x1"] == element["x2"]


def extract_coordinates(element, coordinates, attribs: list[str]):
    # Check if the element contains x1, y1, x2, and y2 attributes
    extraction = {}
    for attrib in attribs:
        extraction[attrib] = element.find(f"int[@name='{attrib}']")
    # x1 = element.find("int[@name='x1']")
    # y1 = element.find("int[@name='y1']")
    # x2 = element.find("int[@name='x2']")
    # y2 = element.find("int[@name='y2']")

    if all(elem is not None for elem in extraction.values()):
        # Extract the coordinates and add them to the list
        coordinates.append(
            {
                **{k: int(v.get("value")) for k, v in extraction.items()},
                "name": element.attrib["name"],
            }
        )

    # Recursively call the function for each child element
    for child in element:
        extract_coordinates(child, coordinates, attribs)


def highlight_line(canvas, line):
    x1, y1, x2, y2 = line
    # Convert previous red line into green line, then draw the new red line
    red_pixels = np.where(np.all(canvas == (0, 0, 255), axis=-1))
    canvas[red_pixels] = (0, 255, 0)

    cv2.line(canvas, (x1, y1), (x2, y2), (0, 0, 255), 1)
    cv2.imshow("Highlighted Canvas", cv2.resize(canvas, None, fx=5, fy=5))
    cv2.waitKey(1)


def write_feature(f, x1, y1, x2, y2, name) -> None:
    box = Box(
        left=x1,
        right=x2,
        top=y1,
        bottom=y2,
        name=name,
        offset=True,
    )
    f.write(f"\t{name}: MinimapFeature = MinimapFeature(")
    f.write("\n")
    f.write(f"\t\tleft={box.left},\n")
    f.write(f"\t\tright={box.right},\n")
    f.write(f"\t\ttop={box.top},\n")
    f.write(f"\t\tbottom={box.bottom},\n")
    f.write(f"\t\tname={repr(box.name)},\n")
    f.write("\t)\n")

class FakeMinimap(Minimap):
    map_area_width = MINIMAP_CANVAS_WIDTH
    map_area_height = MINIMAP_CANVAS_HEIGHT

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


def take_position(minimap: Minimap) -> None:
    pt = minimap.get_character_positions(HANDLE)
    assert len(pt) == 1
    pt = pt.pop()
    return pt


if __name__ == "__main__":
    minimap = FakeMinimap()
    map_area_box = minimap.get_map_area_box(HANDLE)
    container = []
    canvas = np.zeros((MINIMAP_VR_HEIGHT, MINIMAP_VR_WIDTH), dtype=np.uint8)

    fh_coords = []
    extract_coordinates(foothold, fh_coords, ["x1", "y1", "x2", "y2", "prev", "next"])
    for coord in fh_coords:
        if is_vertical(coord):
            continue
        x1, y1 = coord["x1"] + MINIMAP_CENTER_X, coord["y1"] + MINIMAP_CENTER_Y
        x2, y2 = coord["x2"] + MINIMAP_CENTER_X, coord["y2"] + MINIMAP_CENTER_Y
        if (
            x1 > canvas.shape[1]
            or x2 > canvas.shape[1]
            or y1 > canvas.shape[0]
            or y2 > canvas.shape[0]
        ):
            breakpoint()
        elif x1 < 0 or x2 < 0 or y1 < 0 or y2 < 0:
            breakpoint()
        cv2.line(canvas, (x1, y1), (x2, y2), (255,), 1)

    rope_coords = []
    extract_coordinates(ropes, rope_coords, ["x", "y1", "y2"])

    for coord in rope_coords:
        x, y1, y2 = (
            coord["x"] + MINIMAP_CENTER_X,
            coord["y1"] + MINIMAP_CENTER_Y,
            coord["y2"] + MINIMAP_CENTER_Y,
        )
        cv2.line(canvas, (x, y1), (x, y2), (255,), 1)
    cv2.imshow("Canvas", cv2.resize(canvas, None, fx=0.5, fy=0.5))
    cv2.waitKey(1)
    mini_canvas = cv2.resize(
        canvas,
        (MINIMAP_CANVAS_WIDTH, MINIMAP_CANVAS_HEIGHT),
        interpolation=cv2.INTER_AREA
    )

    _, binary = cv2.threshold(mini_canvas, BRIGHTNESS_THRESH, 255, cv2.THRESH_BINARY)
    cv2.imshow("Mini Canvas", cv2.resize(binary, None, fx=5, fy=5))
    cv2.waitKey(1)

    highlighted_canvas = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    copied = binary.copy()

    horizontal_lines = []
    vertical_lines = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > 1:
            horizontal_lines.append((x, y, x + w - 1, y))
            cv2.line(copied, (x, y), (x + w - 1, y), (0,), 1)

    contours, _ = cv2.findContours(copied, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        vertical_lines.append((x, y, x, y + h - 1))

    # breakpoint()
    while True:
        colored = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        pos = take_position(minimap)
        cv2.circle(colored, (pos[0], pos[1] + 2), 1, (0, 0, 255), 1)
        cv2.imshow("Position", cv2.resize(colored, None, fx=5, fy=5))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), "w") as f:
        f.write(
            """from royals.model.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)
    """
        )
        f.write("\n")
        f.write("\n")
        f.write(
            f'class {OUTPUT_NAME.removesuffix(".py").replace("_", " ").title().replace(" ", "")}Minimap(MinimapPathingMechanics):\n'
        )
        f.write("\n")
        f.write(f"\tmap_area_width = {MINIMAP_CANVAS_WIDTH}\n")
        f.write(f"\tmap_area_height = {MINIMAP_CANVAS_HEIGHT}\n")
        f.write(f"\tminimap_speed = {PHYSICS_SPEED / VRWidth * MINIMAP_CANVAS_WIDTH}\n")
        f.write(f"\tjump_height = {VRJumpHeight / VRHeight * MINIMAP_CANVAS_HEIGHT}\n")
        f.write(f"\tjump_distance = {VRJumpWidth / VRWidth * MINIMAP_CANVAS_WIDTH}\n")
        f.write(
            f"\tteleport_h_dist = {TELEPORT_DISTANCE / VRWidth * MINIMAP_CANVAS_WIDTH}\n"
        )

        for line in horizontal_lines + vertical_lines:
            highlight_line(highlighted_canvas, line)
            feature_name = input("Feature name: ")
            if feature_name.upper() == "SKIP":
                continue
            elif feature_name.upper() == "EXIT":
                break
            write_feature(f, *line, feature_name)

