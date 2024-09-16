import cv2
import numpy as np
import os
import xml.etree.ElementTree as ElementTree
from paths import ROOT

# According to Copilot:
# x: The x-coordinate of the object in the map.
# y: The y-coordinate of the object in the map.
# z: The z-index of the object, which determines the drawing order (higher values are drawn on top of lower values).
# f: The flip value, which indicates whether the object should be flipped horizontally (1 for flipped, 0 for not flipped).
# zM: The zoom multiplier, which scales the object (1 means no scaling, values greater than 1 scale up, and values less than 1 scale down).
# r: The rotation value, which specifies the rotation angle of the object in degrees.


tree = ElementTree.parse(
    os.path.join(ROOT, "royals/assets/game_files/maps/PathOfTime1.xml")
)
root = tree.getroot()

# Find the "foothold" element
foothold = root.find(".//imgdir[@name='foothold']")
portals = root.find(".//imgdir[@name='portal']")
ropes = root.find(".//imgdir[@name='ladderRope']")

# Find the info section
info_section = root.find(".//imgdir[@name='info']")

minimap_section = root.find(".//imgdir[@name='miniMap']")

# Extract VR coordinates
VRLeft = int(info_section.find("int[@name='VRLeft']").attrib["value"])
VRTop = int(info_section.find("int[@name='VRTop']").attrib["value"])
VRRight = int(info_section.find("int[@name='VRRight']").attrib["value"])
VRBottom = int(info_section.find("int[@name='VRBottom']").attrib["value"])
VRWidth = VRRight - VRLeft
VRHeight = VRBottom - VRTop

minimap_vr_width = int(minimap_section.find("int[@name='width']").attrib["value"])
minimap_vr_height = int(minimap_section.find("int[@name='height']").attrib["value"])
minimap_center_x = int(minimap_section.find("int[@name='centerX']").attrib["value"])
minimap_center_y = int(minimap_section.find("int[@name='centerY']").attrib["value"])

minimap_canvas_width = int(
    minimap_section.find("canvas[@name='canvas']").attrib["width"]
)
minimap_canvas_height = int(
    minimap_section.find("canvas[@name='canvas']").attrib["height"]
)

scaleX = minimap_vr_width / minimap_canvas_width
scaleY = minimap_vr_height / minimap_canvas_height

canvas = np.zeros((minimap_vr_height, minimap_vr_width, 3), dtype=np.uint8)
# breakpoint()
#
# def map_to_canvas(x, y):
#     # canvas_x = int((x - VRLeft) / (VRRight - VRLeft) * canvas_width)
#     # canvas_y = int((y - VRTop) / (VRBottom - VRTop) * canvas_height)
#     canvas_x = int((x - VRLeft) * scaleX)
#     canvas_y = int((y - VRTop) * scaleY)
#     return canvas_x, canvas_y


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


fh_coords = []
extract_coordinates(foothold, fh_coords, ["x1", "y1", "x2", "y2", "prev", "next"])

for coord in fh_coords:
    x1, y1 = coord["x1"] + minimap_center_x, coord["y1"] + minimap_center_y
    x2, y2 = coord["x2"] + minimap_center_x, coord["y2"] + minimap_center_y
    if (
        x1 > canvas.shape[1]
        or x2 > canvas.shape[1]
        or y1 > canvas.shape[0]
        or y2 > canvas.shape[0]
    ):
        breakpoint()
    elif x1 < 0 or x2 < 0 or y1 < 0 or y2 < 0:
        breakpoint()
    prev = coord["prev"]
    next = coord["next"]
    cv2.line(canvas, (x1, y1), (x2, y2), (255, 255, 255), 1)
    cv2.imshow("Canvas", cv2.resize(canvas, None, fx=0.5, fy=0.5))
    cv2.waitKey(1)
    print("Name:", coord["name"], "Prev:", prev, "Next:", next)
portals_coords = []
extract_coordinates(portals, portals_coords, ["x", "y"])

for coord in portals_coords:
    print(coord)
    x, y = coord["x"] + minimap_center_x, coord["y"] + minimap_center_y
    cv2.circle(canvas, (x, y), 1, (0, 255, 0), 1)
    cv2.imshow("Canvas", cv2.resize(canvas, None, fx=1, fy=1))
    # cv2.imshow('Canvas', canvas)
    cv2.waitKey(1)

rope_coords = []
extract_coordinates(ropes, rope_coords, ["x", "y1", "y2"])

for coord in rope_coords:
    x, y1, y2 = (
        coord["x"] + minimap_center_x,
        coord["y1"] + minimap_center_y,
        coord["y2"] + minimap_center_y,
    )
    cv2.line(canvas, (x, y1), (x, y2), (0, 0, 255), 1)
cv2.imshow("Canvas", cv2.resize(canvas, None, fx=0.5, fy=0.5))
# cv2.imshow('Canvas', canvas)
cv2.waitKey(1)
breakpoint()

from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler


HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)


class FakeMinimap(Minimap):
    map_area_width = minimap_canvas_width
    map_area_height = minimap_canvas_height

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


minimap = FakeMinimap()
map_area_box = minimap.get_map_area_box(HANDLE)


def translate_to_vr(minimap_x, minimap_y):
    # vr_width = VRRight - VRLeft
    # vr_height = VRBottom - VRTop
    # vr_x = minimap_x / map_area_box.width * vr_width + VRLeft
    # vr_y = minimap_y / map_area_box.height * vr_height + VRTop
    return round(minimap_x * scaleX), round(minimap_y * scaleY)


gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
while True:
    copied = canvas.copy()
    char_pos = minimap.get_character_positions(HANDLE).pop()
    gray[char_pos[1], char_pos[0]] = 200
    # breakpoint()
    translated = translate_to_vr(*char_pos)
    adjusted = (translated[0] + 5, translated[1] + 60)
    # translated_min = translate_to_vr(*[i - 1 for i in char_pos])
    # translated_plus = translate_to_vr(char_pos[0], char_pos[1] + 1)
    # cv2.circle(copied, (char_pos[0] - 2, char_pos[1] + 7), 1, (255, 0, 0), 1)
    cv2.circle(copied, translated, 1, (0, 255, 0), 3)
    cv2.circle(copied, adjusted, 1, (0, 0, 255), 3)
    # cv2.circle(copied, translated_min, 1, (255, 255, 0), 3)
    # cv2.circle(copied, translated_plus, 1, (0, 255, 255), 3)
    # test = translate_to_vr(char_pos[0]-1, char_pos[1]+8)
    # cv2.circle(canvas, map_to_canvas(*test), 1, (0, 0, 255), 5)
    cv2.imshow("Canvas", cv2.resize(copied, None, fx=1, fy=1))
    cv2.waitKey(1)

# Extract coordinates and draw lines
# if foothold is not None:
#     for sub_element in foothold.findall('imgdir'):
#         for sub_sub_element in sub_element:
#             x1 = int(sub_sub_element.find("int[@name='x1']").attrib['value'])
#             y1 = int(sub_sub_element.find("int[@name='y1']").attrib['value'])
#             x2 = int(sub_sub_element.find("int[@name='x2']").attrib['value'])
#             y2 = int(sub_sub_element.find("int[@name='y2']").attrib['value'])
#
#             # Draw line on the canvas
#             cv2.line(canvas, (x1, y1), (x2, y2), (255, 255, 255), 2)
#
# # Display the canvas
# cv2.imshow('Canvas', canvas)
# cv2.waitKey(0)
