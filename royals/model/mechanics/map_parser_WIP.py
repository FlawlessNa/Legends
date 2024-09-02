import cv2
import numpy as np
import os
import xml.etree.ElementTree as ElementTree
from paths import ROOT

tree = ElementTree.parse(os.path.join(ROOT, 'royals/assets/game_files/maps/UluEstate1.xml'))
root = tree.getroot()

# Find the "foothold" element
foothold = root.find(".//imgdir[@name='foothold']")
portals = root.find(".//imgdir[@name='portal']")
ropes = root.find(".//imgdir[@name='ladderRope']")

# VRTop = -666
# VRLeft = -375
# VRBottom = 770
# VRRight = 5140
VRTop = -1200
VRLeft = -830
VRBottom = 310
VRRight = 1170

# Create a blank canvas
# canvas_width = 5619  # Adjust as needed
# canvas_height = 1489  # Adjust as needed
# canvas_width = 2126  # Adjust as needed
# canvas_height = 1672  # Adjust as needed
canvas_width = VRRight - VRLeft  # Adjust as needed
canvas_height = VRBottom - VRTop  # Adjust as needed
canvas = np.zeros((104, 132, 3), dtype=np.uint8)

scaleX = 132 / canvas_width
scaleY = 104 / canvas_height

def map_to_canvas(x, y):
    # canvas_x = int((x - VRLeft) / (VRRight - VRLeft) * canvas_width)
    # canvas_y = int((y - VRTop) / (VRBottom - VRTop) * canvas_height)
    canvas_x = int((x - VRLeft) * scaleX)
    canvas_y = int((y - VRTop) * scaleY)
    return canvas_x, canvas_y


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
        coordinates.append({k: int(v.get('value')) for k, v in extraction.items()})

    # Recursively call the function for each child element
    for child in element:
        extract_coordinates(child, coordinates, attribs)

fh_coords = []
extract_coordinates(foothold, fh_coords, ['x1', 'y1', 'x2', 'y2'])

for coord in fh_coords:
    x1, y1 = map_to_canvas(coord['x1'], coord['y1'])
    x2, y2 = map_to_canvas(coord['x2'], coord['y2'])
    cv2.line(canvas, (x1, y1), (x2, y2), (255, 255, 255), 1)
    cv2.imshow('Canvas', cv2.resize(canvas, None, fx=0.5, fy=0.5))
    cv2.waitKey(1)

portals_coords = []
extract_coordinates(portals, portals_coords, ['x', 'y'])

for coord in portals_coords:
    print(coord)
    x, y = map_to_canvas(coord['x'], coord['y'])
    cv2.circle(canvas, (x, y), 1, (0, 255, 0), 1)
    cv2.imshow('Canvas', cv2.resize(canvas, None, fx=0.5, fy=0.5))
    # cv2.imshow('Canvas', canvas)
    cv2.waitKey(1)

rope_coords = []
extract_coordinates(ropes, rope_coords, ['x', 'y1', 'y2'])

for coord in rope_coords:
    x, y1 = map_to_canvas(coord['x'], coord['y1'])
    x, y2 = map_to_canvas(coord['x'], coord['y2'])
    cv2.line(canvas, (x, y1), (x, y2), (0, 0, 255), 1)
cv2.imshow('Canvas', cv2.resize(canvas, None, fx=1, fy=1))
# cv2.imshow('Canvas', canvas)
cv2.waitKey(1)

from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler


HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)

class FakeMinimap(Minimap):
    map_area_width = 132
    map_area_height = 104
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass

minimap = FakeMinimap()
map_area_box = minimap.get_map_area_box(HANDLE)

def translate_to_vr(minimap_x, minimap_y):
    vr_width = VRRight - VRLeft
    vr_height = VRBottom - VRTop
    vr_x = minimap_x / map_area_box.width * vr_width + VRLeft
    vr_y = minimap_y / map_area_box.height * vr_height + VRTop
    return vr_x, vr_y

gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
while True:
    copied = canvas.copy()
    char_pos = minimap.get_character_positions(HANDLE).pop()
    # gray[char_pos[1] + 7, char_pos[0]-  2] = 200
    # breakpoint()
    # translated = translate_to_vr(*char_pos)
    cv2.circle(copied, (char_pos[0] - 2, char_pos[1] + 7), 1, (255, 0, 0), 1)
    cv2.circle(copied, char_pos, 1, (0, 255, 0), 1)
    # test = translate_to_vr(char_pos[0]-1, char_pos[1]+8)
    # cv2.circle(canvas, map_to_canvas(*test), 1, (0, 0, 255), 5)
    cv2.imshow('Test', cv2.resize(copied, None, fx=3, fy=3))
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
